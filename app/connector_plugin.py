"""Install the real native plugin through the supported Codex CLI registry."""
import json
import re
from .private_files import restrict_file
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from .team_install import InstallError
from .plugin_host import check as check_host

SOURCE=Path(__file__).resolve().parent.parent/'plugins/songban-native'
SELECTOR='songban-connector@songban-local'

def _run(cli,args,env):
 try:r=subprocess.run([cli,*args,'--json'],capture_output=True,text=True,encoding='utf-8',timeout=45,env=env)
 except (OSError,subprocess.TimeoutExpired):raise InstallError('plugin_cli_failed','Codex插件安装命令无法执行或超时，请检查本机Codex安装。',502) from None
 if r.returncode:raise InstallError('plugin_cli_failed','Codex未接受插件安装。原生插件尚未启用，请查看本机插件目录与权限。',502)
 try:return json.loads(r.stdout)
 except ValueError:raise InstallError('plugin_cli_failed','Codex安装返回异常，未确认插件启用。',502) from None

def install_connector_plugin(sid,user_id,connection_id,token,url,home=None,cli=None,probe=None):
 home=Path(home) if home else Path.home()
 codex_home=home/'.codex';base=codex_home/'plugins/songban-local';root=base/'catalog';target=root/'plugins/songban-connector'
 binding=base/'private/connection.json';catalog=root/'.agents/plugins/marketplace.json'
 cli=cli or shutil.which('codex')
 if not cli:raise InstallError('codex_missing','未找到Codex命令行工具，暂不能自动注册原生插件。',409)
 for p in (base,root,target,binding,catalog):
  if p.is_symlink() or not p.resolve().is_relative_to(codex_home.resolve()):raise InstallError('plugin_path_conflict','插件安装位置指向外部，已停止。',409)
 if target.exists() and any(p.is_file() for p in target.rglob('*')) and not (target/'.songban-owned').exists():raise InstallError('plugin_path_conflict','同名插件目录不是松伴创建的，未覆盖。',409)
 env=dict(os.environ);env['CODEX_HOME']=str(codex_home)
 config=codex_home/'config.toml'
 before=tomllib.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
 def unrelated(d):
  d=json.loads(json.dumps(d))
  for key,own in (('plugins',SELECTOR),('marketplaces','songban-local')):
   if isinstance(d.get(key),dict):
    d[key].pop(own,None)
    if not d[key]:d.pop(key)
  return d
 files={str(p.relative_to(SOURCE)):p.read_bytes() for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 # Older local Codex hosts do not expand PLUGIN_ROOT in MCP arguments/cwd.
 # Preserve the portable layout for modern/Windows hosts and the working legacy path otherwise.
 try:
  version=subprocess.run([cli,'--version'],capture_output=True,text=True,encoding='utf-8',timeout=5,env=env)
  match=re.search(r'(\d+)\.(\d+)\.',version.stdout)
  modern=bool(match and tuple(map(int,match.groups()))>=(0,165))
 except (OSError,subprocess.SubprocessError):modern=False
 portable=os.name=='nt' or modern
 mcp={'mcpServers':{'songban':{'type':'stdio','command':Path(sys.executable).name if portable else sys.executable,'args':['${PLUGIN_ROOT}/server.py' if portable else str(target/'server.py'),'--binding',str(binding)],'cwd':'${PLUGIN_ROOT}' if portable else str(target),'env':{'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH',''),'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}}}}
 files['.mcp.json']=json.dumps(mcp).encode();files['mcp.json']=json.dumps({'$schema':'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json',**mcp}).encode();files['.songban-owned']=b'1.0.0\n'
 cat={'name':'songban-local','interface':{'displayName':'松伴本机插件'},'plugins':[{'name':'songban-connector','source':{'source':'local','path':'./plugins/songban-connector'},'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]}
 writes={target/k:v for k,v in files.items()}
 writes[catalog]=json.dumps(cat,ensure_ascii=False,indent=2).encode()
 writes[binding]=json.dumps({'url':url,'team_id':sid,'token':token,'connection_id':connection_id},ensure_ascii=False).encode()
 backup=base/'backups'/connection_id;original={};written={};previous=None
 if binding.exists():
  try:previous=json.loads(binding.read_text(encoding='utf-8-sig')).get('connection_id')
  except ValueError:raise InstallError('plugin_binding_invalid','现有连接配置无法读取，未覆盖。',409)
 try:
  for p,data in writes.items():
   # Refuse symlinks in every existing ancestor, not just the final file.
   if any(q.is_symlink() for q in (p,*p.parents) if q.is_relative_to(base)):raise InstallError('plugin_path_conflict','插件目录包含链接，已停止。',409)
   original[p]=p.read_bytes() if p.exists() else None
   if original[p] is not None:
    b=backup/p.relative_to(base);b.parent.mkdir(parents=True,exist_ok=True,mode=0o700);b.write_bytes(original[p]);restrict_file(b)
   p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
   with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as f:f.write(data);tmp=Path(f.name)
   restrict_file(tmp);tmp.replace(p);written[p]=data
  if probe:ok=probe(target,binding)
  else:
   r=subprocess.run([sys.executable,str(target/'server.py'),'--binding',str(binding),'--check'],capture_output=True,text=True,encoding='utf-8',timeout=25)
   ok=r.returncode==0
  if not ok:raise InstallError('plugin_connection_failed','插件无法读取团队。请确认松伴服务、连接有效期及本机网络权限；本次绑定已回退。',502)
  _run(cli,['plugin','marketplace','add',str(root)],env)
  _run(cli,['plugin','add',SELECTOR],env)
  state=_run(cli,['plugin','list'],env)
  entries=state.get('installed',[]) if isinstance(state,dict) else []
  enabled=any(x.get('name')=='songban-connector' and x.get('enabled') is True for x in entries)
  if not enabled:raise InstallError('plugin_not_enabled','文件已生成，但Codex未确认插件启用。请在插件目录查看松伴连接器。',502)
  try:host=check_host(home,home,cli=cli)
  except (OSError,RuntimeError,subprocess.SubprocessError):
   raise InstallError('plugin_not_loaded','独立宿主未能完成工具加载检查，本次绑定已回退。请检查Codex运行时后重试。',502) from None
  if not host['upload_tool_loaded'] or host['loader_errors']:
   raise InstallError('plugin_not_loaded','Codex已注册插件，但宿主未能加载同步工具，本次绑定已回退。请核对运行时和宿主版本。',502)
  after=tomllib.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
  if unrelated(before)!=unrelated(after):raise InstallError('plugin_config_changed','安装后检测到其他设置发生变化，请查看备份；未声称安装成功。',409)
  return {'installed':True,'kind':'native-plugin','tool':'Codex','registered':True,'enabled':True,'host_tools_loaded':True,'bridge_verified':True,'client_loaded':False,'project_dir':str(target),'config_file':str(binding),'backup_dir':str(backup),'previous_connection_id':previous,'notice':'原生插件「松伴连接器」已注册并启用，团队连接和独立宿主工具加载已验证。请在输入框加号的插件入口搜索该名称。当前窗口是否已刷新尚未验证；若未出现，请先新建对话并检查插件目录。安装不代表所有聊天自动上传，仅共享你选择或明确授权的对话。'}
 except Exception:
  if SELECTOR not in before.get('plugins',{}):
   try:_run(cli,['plugin','remove',SELECTOR],env)
   except InstallError:pass
  if 'songban-local' not in before.get('marketplaces',{}):
   try:_run(cli,['plugin','marketplace','remove','songban-local'],env)
   except InstallError:pass
  for p,data in reversed(list(written.items())):
   if p.exists() and p.read_bytes()==data:
    if original[p] is None:p.unlink()
    else:p.write_bytes(original[p])
  raise
