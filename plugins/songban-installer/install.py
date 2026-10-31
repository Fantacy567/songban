#!/usr/bin/env python3
"""Run on the visitor's own computer. Does not invoke a model or scan chats."""
import argparse,json,sys
from pathlib import Path

def main():
 # Keep Chinese instructions readable when Windows redirects output using an ANSI code page.
 for stream in (sys.stdout,sys.stderr):
  if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
 if sys.version_info<(3,11):
  print('需要 Python 3.11 或以上。请安装后重新运行。');return 2
 parser=argparse.ArgumentParser(description='安装网页中所选队伍的松伴连接器')
 parser.add_argument('--check',action='store_true',help='只检查团队连接，不写入工具配置')
 parser.add_argument('--project-dir',help='兼容连接使用的本机项目目录')
 parser.add_argument('--home',type=Path,default=Path.home(),help='Codex配置所在的用户目录（默认当前用户）')
 args=parser.parse_args();root=Path(__file__).resolve().parent
 sys.path.insert(0,str(root))
 from app.private_files import restrict_file
 from app.team_install import InstallError,install_project
 from app.connector_plugin import install_connector_plugin
 try:
  file=root/'connection.json';restrict_file(file);binding=json.loads(file.read_text(encoding='utf-8-sig'))
  options={k:binding[k] for k in ('base_path','demo_session') if k in binding}
  if args.check:
   sys.path.insert(0,str(root/'plugins/songban-native'))
   from transport import binding as read_binding,request
   request(read_binding(file),'/context');print('团队连接检查通过。');return 0
  tool=binding['tool']
  if tool=='connector-plugin':
   result=install_connector_plugin(binding['team_id'],binding['user_id'],binding['connection_id'],binding['token'],binding['url'],home=args.home,binding_options=options)
  elif tool in ('codex','cursor','workbuddy'):
   project=args.project_dir or input('请填写这台电脑上正在开发的项目文件夹完整路径：').strip()
   result=install_project(project,tool,binding['url'],binding['team_id'],binding['user_id'],binding['connection_id'],binding['token'],binding_options=options)
  else:raise InstallError('unsupported_tool','安装方式不受支持，请重新下载。')
  print('安装成功，已验证当前队伍连接。')
  print(result.get('notice','回到所选工具重新打开项目。'))
  return 0
 except (InstallError,OSError,ValueError,KeyError) as error:
  print('安装未完成：'+getattr(error,'message','请检查安装包、Python、工具安装和本机文件权限。'))
  return 1
 except Exception as error:
  # Network errors from the explicit check must not reveal a private binding.
  print('连接检查未通过：'+(str(error) if type(error).__name__=='ConnectorError' else '请检查服务和网络后重试。'))
  return 1
if __name__=='__main__':raise SystemExit(main())
