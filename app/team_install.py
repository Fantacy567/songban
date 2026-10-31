"""Explicit, project-scoped local installer. Never changes global/model settings."""
import ipaddress
import json
from .private_files import restrict_file
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.parse import urlsplit

TOOLS={'codex':('.codex/config.toml','Codex'),'workbuddy':('.workbuddy/mcp.json','WorkBuddy'),'cursor':('.cursor/mcp.json','Cursor')}
ENTRY='songban-team'
BEGIN='# BEGIN SONGBAN TEAM MCP\n'
END='# END SONGBAN TEAM MCP'
PLUGIN_ROOT=Path(__file__).resolve().parent.parent/'plugins/songban-team'


class InstallError(Exception):
    def __init__(self,code,message,status=422):
        self.code,self.message,self.status=code,message,status
        super().__init__(message)


def is_local_request(request):
    try:
        ip=ipaddress.ip_address(request.client.host)
        parts=urlsplit(str(request.url))
        origin=request.headers.get('origin')
        forwarded=any(k in request.headers for k in ('forwarded','x-forwarded-for','x-forwarded-host'))
        return ip.is_loopback and parts.hostname in ('127.0.0.1','localhost','::1') and not forwarded and (not origin or origin==f'{parts.scheme}://{parts.netloc}') and request.headers.get('sec-fetch-site','same-origin') not in ('cross-site','same-site')
    except (ValueError,AttributeError):return False


def project_path(raw):
    if not isinstance(raw,str) or not raw or len(raw)>1000 or '\x00' in raw:
        raise InstallError('invalid_project','请选择已存在的项目文件夹。')
    root=Path(raw).expanduser().resolve()
    if not root.is_dir() or root==Path.home().resolve() or len(root.parts)<3:
        raise InstallError('invalid_project','请选择具体项目文件夹，不能安装到整个用户目录或系统根目录。')
    if any(root==p or p in root.parents for p in (Path('/System'),Path('/Applications'),Path('/usr'),Path('/etc'),Path('/bin'),Path('/sbin'))):
        raise InstallError('invalid_project','请选择自己的工作项目，不要选择系统目录。')
    return root


def target_path(root,relative):
    p=root/relative
    if p.is_symlink() or not p.resolve().is_relative_to(root):
        raise InstallError('linked_config','项目配置指向其他目录，已停止安装，避免改动全局配置。')
    return p


def config_text(root,tool,before,entry):
    if tool=='codex':
        try:original=tomllib.loads(before or '')
        except (ValueError,TypeError):raise InstallError('invalid_config','现有Codex配置无法读取，未覆盖；请先修复该文件。') from None
        servers=original.get('mcp_servers',{})
        if not isinstance(servers,dict):raise InstallError('invalid_config','现有MCP配置不是表格，未覆盖。')
        exists=servers.get(ENTRY)
        marker=BEGIN in before and END in before
        expected=str(root/'.songban/connection.json')
        if exists and (not marker or not isinstance(exists,dict) or exists.get('env',{}).get('SONGBAN_CONFIG')!=expected):
            raise InstallError('config_conflict','已有同名的其他连接，未覆盖。请先在工具里核对songban-team。',409)
        if marker:
            if before.count(BEGIN)!=1 or before.count(END)!=1:raise InstallError('config_conflict','安装标记不唯一，请先核对。',409)
            before=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END)+r'\n?', '',before,flags=re.S)
        text=before.rstrip()+'\n\n'+BEGIN+'[mcp_servers.songban-team]\ncommand = '+json.dumps(entry['command'],ensure_ascii=False)+'\nargs = '+json.dumps(entry['args'],ensure_ascii=False)+'\n[mcp_servers.songban-team.env]\n'+''.join(k+' = '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in entry['env'].items())+END+'\n'
        try:after=tomllib.loads(text)
        except ValueError:raise InstallError('invalid_config','无法安全合并Codex连接，未改动模型配置。') from None
        # Prove that every setting other than our MCP entry is semantically unchanged.
        def without_ours(data):
            data=json.loads(json.dumps(data,default=str));m=data.get('mcp_servers',{});m.pop(ENTRY,None)
            if not m:data.pop('mcp_servers',None)
            return data
        if without_ours(after)!=without_ours(original):raise InstallError('config_conflict','合并会改变其他设置，已停止。',409)
        return text
    try:data=json.loads(before) if before.strip() else {}
    except ValueError:raise InstallError('invalid_config','现有MCP配置不是有效JSON，未覆盖；请先修复。') from None
    if not isinstance(data,dict) or not isinstance(data.get('mcpServers',{}),dict):raise InstallError('invalid_config','现有MCP配置结构不正确，未覆盖。')
    servers=data.setdefault('mcpServers',{});exists=servers.get(ENTRY)
    if exists and (not isinstance(exists,dict) or exists.get('env',{}).get('SONGBAN_CONFIG')!=str(root/'.songban/connection.json')):
        raise InstallError('config_conflict','已有同名的其他连接，未覆盖。',409)
    servers[ENTRY]=entry
    return json.dumps(data,ensure_ascii=False,indent=2)+'\n'


def probe_bridge(bridge,config,root):
    env={k:v for k,v in os.environ.items() if not k.startswith('SONGBAN_')}
    env.update({'SONGBAN_CONFIG':str(config),'SONGBAN_PROJECT_ROOT':str(root),'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
    requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'songban-installer','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'}, {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'songban_get_team_context','arguments':{}}}]
    try:
        result=subprocess.run([sys.executable,str(bridge),'mcp'],input='\n'.join(json.dumps(r) for r in requests)+'\n',text=True,encoding='utf-8',capture_output=True,env=env,cwd=root,timeout=26,check=False)
        responses=[json.loads(l) for l in result.stdout.splitlines() if l.strip()]
        reply=next(r for r in responses if r.get('id')==2)['result']
        if result.returncode or reply.get('isError'):raise ValueError()
        data=json.loads(reply['content'][0]['text'])
        if not isinstance(data.get('active_plan'),dict) or not isinstance(data.get('direction'),dict):raise ValueError()
        return {'bridge_verified':True,'plan_version':data['plan_version'],'client_loaded':False}
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,StopIteration,IndexError,TypeError):
        raise InstallError('connection_check_failed','插件未能取回团队任务，已回退本次安装。请检查团队地址和网络后重试。',502) from None


def install_project(root,tool,url,sid,actor_id,connection_id,token,probe=None,binding_options=None):
    root=project_path(str(root))
    if tool not in TOOLS:raise InstallError('unsupported_tool','当前一键安装支持Codex、WorkBuddy和Cursor；其他工具请使用通用插件。')
    u=urlsplit(url)
    if not (u.scheme=='https' or (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1'))) or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise InstallError('invalid_url','团队地址不符合连接要求。')
    private=target_path(root,'.songban');private.mkdir(mode=0o700,exist_ok=True)
    backup=target_path(root,'.songban/install-backups/'+connection_id)
    lock=target_path(root,'.songban/install.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    except FileExistsError:raise InstallError('install_busy','这个项目正在安装，稍后再试；若上次意外中断，请先检查.songban/install.lock。',409) from None
    originals={};written={}
    try:
        meta=target_path(root,'.songban/install-state.json')
        old=json.loads(meta.read_text(encoding='utf-8-sig')) if meta.exists() else {}
        if old.get('user_id') and old['user_id']!=actor_id:raise InstallError('installation_owner_conflict','这个项目已有另一位成员的个人连接，请各自在自己的项目副本安装。',409)
        config=target_path(root,TOOLS[tool][0]);before=config.read_text(encoding='utf-8-sig') if config.exists() else ''
        bridge=target_path(root,'.songban/plugin/bridge.py')
        private_config=target_path(root,'.songban/connection.json')
        entry={'command':sys.executable,'args':[str(bridge),'mcp'],'env':{'SONGBAN_CONFIG':str(private_config),'SONGBAN_PROJECT_ROOT':str(root),'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}}
        merged=config_text(root,tool,before,entry)
        files={config:merged.encode(),private_config:json.dumps({'url':url,'team_id':sid,'token':token,'project_root':str(root),**(binding_options or {})},ensure_ascii=False).encode()}
        ignore=target_path(root,'.songban/.gitignore');files[ignore]=b'*\n'
        for rel in ('bridge.py','README.md','mcp.example.json','update.example.json','skills/songban-team/SKILL.md','skills/songban-team/agents/openai.yaml'):
            files[target_path(root,'.songban/plugin/'+rel)]=(PLUGIN_ROOT/rel).read_bytes()
        if tool=='codex':
            skill=target_path(root,'.agents/skills/songban-team/SKILL.md')
            if skill.exists() and '松伴团队联络员' not in skill.read_text(encoding='utf-8-sig'):raise InstallError('skill_conflict','已有同名技能，未覆盖。',409)
            files[skill]=(PLUGIN_ROOT/'skills/songban-team/SKILL.md').read_bytes()
            files[target_path(root,'.agents/skills/songban-team/agents/openai.yaml')]=(PLUGIN_ROOT/'skills/songban-team/agents/openai.yaml').read_bytes()
        gitignore=target_path(root,'.gitignore');ignore_text=gitignore.read_text(encoding='utf-8-sig') if gitignore.exists() else ''
        if '.songban/' not in ignore_text.splitlines():files[gitignore]=(ignore_text.rstrip()+'\n\n# 松伴个人连接（含私有凭证，不提交）\n.songban/\n').encode()
        backup.mkdir(parents=True,mode=0o700)
        backup_ignore=backup/'.gitignore';backup_ignore.write_text('*\n',encoding='utf-8');restrict_file(backup_ignore)
        for target,content in files.items():
            target_path(root,str(target.relative_to(root)))
            original=target.read_bytes() if target.exists() else None;originals[target]=original
            if original is not None:
                dest=backup/str(target.relative_to(root));dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original);restrict_file(dest)
            target.parent.mkdir(parents=True,exist_ok=True)
            # Atomic replace and fail if another process changed the file since snapshot.
            if (target.read_bytes() if target.exists() else None)!=original:raise InstallError('config_changed','安装期间配置被其他程序修改，已停止。',409)
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as f:
                f.write(content);temp=Path(f.name)
            restrict_file(temp);os.replace(temp,target);written[target]=content
        check=(probe or probe_bridge)(bridge,private_config,root)
        if not check.get('bridge_verified'):raise InstallError('connection_check_failed','连接检查未通过，已回退。',502)
        state={'user_id':actor_id,'team_id':sid,'connection_id':connection_id,'tool':tool,'installed_at':int(time.time()),'client_loaded':False}
        meta_before=meta.read_bytes() if meta.exists() else None
        with tempfile.NamedTemporaryFile(dir=meta.parent,delete=False) as f:
            f.write(json.dumps(state,ensure_ascii=False).encode());temp=Path(f.name)
        restrict_file(temp)
        if (meta.read_bytes() if meta.exists() else None)!=meta_before:
            temp.unlink(missing_ok=True)
            raise InstallError('config_changed','安装期间连接记录已被修改，已停止。',409)
        os.replace(temp,meta)
        return {'installed':True,'tool':TOOLS[tool][1],'project_dir':str(root),'config_file':str(config),'connection_id':connection_id,'backup_dir':str(backup),'bridge_verified':True,'client_loaded':False,'previous_connection_id':old.get('connection_id') if old.get('team_id')==sid else None,'notice':'已安装并验证团队连接。请在所选工具中重新打开这个项目；若提示信任项目或启用连接，请按工具提示确认。首次让智能体读取松伴方向和本人任务。'}
    except Exception:
        for target,content in reversed(list(written.items())):
            # Never overwrite unrelated concurrent changes while rolling back.
            if target.exists() and target.read_bytes()==content:
                original=originals[target]
                if original is None:target.unlink()
                else:target.write_bytes(original)
        raise
    finally:lock.unlink(missing_ok=True)
