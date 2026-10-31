"""Exercise Codex's actual plugin/MCP loader without a model turn or chat upload."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

def check(home,cwd,cli='codex'):
 env=dict(os.environ);env['CODEX_HOME']=str(Path(home)/'.codex')
 p=subprocess.Popen([cli,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env=env,cwd=cwd,bufsize=1)
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
  result=rpc(2,'mcpServerStatus/list',{'limit':100})
  servers=result.get('data',[])
  own=[s for s in servers if 'songban' in s.get('name','').lower()]
  names=[]
  for s in own:
   ts=s.get('tools',{})
   names.extend(ts.keys() if isinstance(ts,dict) else [x.get('name') for x in ts])
  return {'host_loader_tested':True,'servers':[s.get('name') for s in own],'tool_names':names,'loader_errors':errors,'upload_tool_loaded':any('songban_sync_selected_turn' in (x or '') for x in names)}
 finally:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
  for stream in (p.stdin,p.stdout,p.stderr):stream.close()
