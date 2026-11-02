"""Exercise Codex's actual plugin/MCP loader without a model turn or chat upload."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import tomllib
import tempfile

def check(home,cwd,cli=None):
 desktop=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
 cli=cli or (str(desktop) if desktop.is_file() else 'codex')
 # Windows CreateProcess does not search PATHEXT for npm CLI shims.
 cli=shutil.which(cli) or cli
 env=dict(os.environ);env['CODEX_HOME']=str(Path(home)/'.codex')
 # Probe only this plugin; unrelated remote integrations can otherwise delay
 # discovery. Overrides affect this child process, never the user's settings.
 config=Path(home)/'.codex/config.toml'
 settings=tomllib.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
 unrelated=any(name!='songban-connector@songban-local' and value.get('enabled',True) for name,value in settings.get('plugins',{}).items()) or any('songban' not in name.lower() and value.get('enabled',True) for name,value in settings.get('mcp_servers',{}).items())
 if unrelated:
  # Register the exact installed local package in a temporary Codex home.
  # This avoids waiting on unrelated remote marketplaces and MCP processes.
  # Its MCP configuration still points to the real private binding file.
  with tempfile.TemporaryDirectory(prefix='songban-host-probe-') as folder:
   probe_home=Path(folder);probe_env=dict(os.environ);probe_env['CODEX_HOME']=str(probe_home/'.codex')
   (probe_home/'.codex').mkdir()
   catalog=Path(home)/'.codex/plugins/songban-local/catalog'
   for args in (['plugin','marketplace','add',str(catalog)],['plugin','add','songban-connector@songban-local']):
    setup=subprocess.run([cli,*args,'--json'],capture_output=True,text=True,encoding='utf-8',timeout=20,env=probe_env,cwd=cwd)
    if setup.returncode:raise RuntimeError('松伴插件隔离宿主准备失败')
   result=check(probe_home,cwd,cli)
   return {**result,'other_plugins_disabled_for_probe_only':True,'isolated_plugin_probe':True}
 overrides=[]
 for name in settings.get('plugins',{}):
  if name!='songban-connector@songban-local':overrides.extend(['-c','plugins.'+json.dumps(name)+'.enabled=false'])
 for name in settings.get('mcp_servers',{}):
  if 'songban' not in name.lower():overrides.extend(['-c','mcp_servers.'+json.dumps(name)+'.enabled=false'])
 p=subprocess.Popen([cli,*overrides,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env=env,cwd=cwd,bufsize=1)
 q=queue.Queue();errors=[]
 def lines():
  for line in p.stdout:
   try:q.put(json.loads(line))
   except ValueError:pass
 def logs():
  for line in p.stderr:
   if 'songban' in line.lower() and ('failed' in line.lower() or 'missing field' in line.lower()):errors.append(line[:600])
 threading.Thread(target=lines,daemon=True).start();threading.Thread(target=logs,daemon=True).start()
 def rpc(ident,method,params):
  p.stdin.write(json.dumps({'id':ident,'method':method,'params':params})+'\n');p.stdin.flush()
  deadline=time.monotonic()+30
  while time.monotonic()<deadline:
   try:r=q.get(timeout=1)
   except queue.Empty:continue
   if r.get('id')==ident:
    if 'error' in r:raise RuntimeError(str(r['error']))
    return r.get('result')
  raise RuntimeError('宿主加载检查超时')
 try:
  rpc(1,'initialize',{'clientInfo':{'name':'songban-loader-check','version':'0.9.1'},'capabilities':{'experimentalApi':True}})
  p.stdin.write(json.dumps({'method':'initialized'})+'\n');p.stdin.flush()
  # Tool discovery may finish after initialize, especially just after plugin registration.
  # Poll read-only status briefly; an empty first response is not a loading failure.
  due=time.monotonic()+8
  ident=2;own=[];names=[]
  while True:
   result=rpc(ident,'mcpServerStatus/list',{'limit':100});ident+=1
   servers=result.get('data',[])
   own=[s for s in servers if 'songban' in s.get('name','').lower()]
   names=[]
   for s in own:
    ts=s.get('tools',{})
    names.extend(ts.keys() if isinstance(ts,dict) else [x.get('name') for x in ts])
   loaded=any('songban_sync_selected_turn' in (x or '') for x in names)
   if loaded or errors or time.monotonic()>=due:break
   time.sleep(.25)
  return {'host_loader_tested':True,'other_plugins_disabled_for_probe_only':bool(overrides),'servers':[s.get('name') for s in own],'tool_names':names,'loader_errors':errors,'upload_tool_loaded':loaded}
 finally:
  # EOF lets Codex shut down its MCP children before their cache directories
  # are updated or removed; force-terminating the parent leaves Windows locks.
  p.stdin.close()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:
   p.terminate()
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for stream in (p.stdin,p.stdout,p.stderr):stream.close()
