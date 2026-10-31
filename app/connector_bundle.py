"""Build an authenticated per-member installer in memory; never install on the web server."""
import io,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build_bundle(binding):
 data=io.BytesIO();prefix='songban-connector-install/'
 with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
  def write(name,content,mode=0o600):
   entry=zipfile.ZipInfo(prefix+name);entry.external_attr=(0o100000|mode)<<16;entry.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(entry,content)
  write('connection.json',json.dumps(binding,ensure_ascii=False))
  write('install.py',(ROOT/'plugins/songban-installer/install.py').read_bytes())
  write('app/__init__.py',b'')
  for name in ['connector_plugin.py','team_install.py','private_files.py','plugin_host.py']:write('app/'+name,(ROOT/'app'/name).read_bytes())
  for folder in ['songban-native','songban-team']:
   base=ROOT/'plugins'/folder
   for file in base.rglob('*'):
    if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':write('plugins/'+folder+'/'+file.relative_to(base).as_posix(),file.read_bytes())
  write('安装松伴.command','#!/bin/zsh\ncd -- "$(dirname -- "$0")"\npython3 install.py\nprintf "\\n按回车关闭窗口…"\nread -r\n',0o700)
  write('安装松伴.cmd','@echo off\r\ncd /d "%~dp0"\r\nwhere py >nul 2>&1\r\nif %errorlevel% equ 0 (py -3 install.py) else (python install.py)\r\npause\r\n')
  write('请先阅读.txt','松伴连接器 · 已绑定本人当前队伍\n\n1. 完整解压安装包。需要 Python 3.11+，并安装所选的 Codex / Cursor / WorkBuddy。\n2. macOS：双击“安装松伴.command”。Windows：双击“安装松伴.cmd”。\n   也可在终端进入解压文件夹，运行 python3 install.py。\n3. 原生插件安装后，在 Codex 插件入口选择“松伴连接器”。兼容方式会询问这台电脑上的项目路径。\n\n网页下载不是已安装；运行后会检查团队连接和工具注册。失败会说明原因并恢复原配置。不会修改模型/provider，不扫描其他聊天。\n安装包内的 connection.json 包含本人连接凭证，请勿分享安装包或提交Git。可在网页“我的连接”撤销。\n演示包仅用于当前虚构会话，重开演示/服务重启后需要重新下载。临时公网地址要求服务和隧道保持在线。\n')
  write('.gitignore','connection.json\n__pycache__/\n')
 return data.getvalue()
