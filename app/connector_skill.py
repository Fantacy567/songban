"""Install a discoverable explicit-only skill, separate from project MCP wiring."""
import json
from .private_files import restrict_file
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from .team_install import InstallError

SOURCE=Path(__file__).resolve().parent.parent/'plugins/songban-connector'
FILES=('SKILL.md','agents/openai.yaml','scripts/connector.py')


def install_connector_skill(sid,user_id,connection_id,token,url,home=None,connection_file=None,probe=None):
    home=Path(home) if home else Path.home()
    target=home/'.codex/skills/songban-connector'
    if target.is_symlink() or not target.resolve().is_relative_to(home.resolve()):raise InstallError('linked_skill','技能目录指向其他位置，未安装。')
    marker=target/'SKILL.md'
    if marker.exists() and 'name: songban-connector' not in marker.read_text(encoding='utf-8-sig'):raise InstallError('skill_conflict','同名目录已有其他技能，未覆盖。',409)
    target.mkdir(parents=True,exist_ok=True,mode=0o700)
    contents={name:(SOURCE/name).read_bytes() for name in FILES}
    bind={'connection_file':str(connection_file)} if connection_file else {'url':url,'team_id':sid,'token':token}
    contents['binding.json']=json.dumps(bind,ensure_ascii=False).encode()
    contents['.gitignore']=b'binding.json\n.install-backups/\n__pycache__/\n'
    backup=target/'.install-backups'/connection_id
    backup.mkdir(parents=True,exist_ok=True,mode=0o700)
    originals={};written={}
    try:
        for rel,data in contents.items():
            file=target/rel
            if file.is_symlink() or not file.resolve().is_relative_to(target.resolve()):raise InstallError('linked_skill','技能文件指向外部，未覆盖。')
            old=file.read_bytes() if file.exists() else None;originals[file]=old
            if old is not None:
                b=backup/rel;b.parent.mkdir(parents=True,exist_ok=True);b.write_bytes(old);restrict_file(b)
            file.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=file.parent,delete=False) as f:f.write(data);tmp=Path(f.name)
            restrict_file(tmp);tmp.replace(file);written[file]=data
        if probe:ok=probe(target)
        else:
            env={k:v for k,v in os.environ.items() if not k.startswith('SONGBAN_')}
            r=subprocess.run([sys.executable,str(target/'scripts/connector.py'),'context','--selected'],capture_output=True,text=True,encoding='utf-8',timeout=25,env=env)
            try:d=json.loads(r.stdout);ok=r.returncode==0 and d.get('team_id')==sid and isinstance(d.get('tasks'),list)
            except ValueError:ok=False
        if not ok:raise InstallError('skill_check_failed','技能未能读取团队方向，已回退本次安装。',502)
        return {'installed':True,'kind':'selected-turn-skill','tool':'松伴连接器','project_dir':str(target),'config_file':str(target/'binding.json'),'backup_dir':str(backup),'bridge_verified':True,'client_loaded':False,'notice':'已安装名为「松伴连接器」的技能。请在对话技能选择器中搜索并附带；也可输入 $songban-connector 或 @ 搜索。若当前列表未更新，新建对话后再看。只有显式选择的回合才应同步。'}
    except Exception:
        for file,data in reversed(list(written.items())):
            if file.exists() and file.read_bytes()==data:
                if originals[file] is None:file.unlink()
                else:file.write_bytes(originals[file])
        raise
