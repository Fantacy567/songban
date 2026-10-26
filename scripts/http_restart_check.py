"""Actual TCP requests and a real subprocess stop/start on a temporary database."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent.parent
out = root / "artifacts"
out.mkdir(exist_ok=True)
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
base = f"http://127.0.0.1:{port}"
process = None
steps = []


def start(env):
    proc = subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port)], cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("测试服务启动失败（可能端口不可用）。")
        try:
            if httpx.get(base+"/health",timeout=.5,trust_env=False).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(.05)
    proc.terminate();proc.wait(timeout=5)
    raise RuntimeError("测试服务未就绪。")


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)


try:
    with tempfile.TemporaryDirectory() as temp:
        env={**os.environ,"DATABASE_PATH":str(Path(temp)/"restart.sqlite3"),"MODEL_API_KEY":"","MODEL_BASE_URL":"","MODEL_NAME":""}
        process=start(env)
        with httpx.Client(base_url=base,timeout=8,trust_env=False) as client:
            payload={"name":"HTTP 重启持久化验证","deadline":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),"members":[{"name":"队长测试","role":"后端","skills":"Python","available_hours":4},{"name":"前端测试","role":"前端","skills":"JavaScript","available_hours":4}]}
            response=client.post('/api/projects',json=payload);assert response.status_code==201
            created=response.json();pid=created['project_id'];headers={"Authorization":"Bearer "+created['invites'][0]['access_token']}
            for kind in ['rules','discussion']:
                response=client.post(f'/api/projects/{pid}/sources',headers=headers,json={"kind":kind,"title":kind,"body":"目标：验证保存、读取与重启后仍在。"});assert response.status_code==201
            response=client.post(f'/api/projects/{pid}/proposals',headers=headers,json={"mode":"local_rules"});assert response.status_code==201
            draft=response.json();response=client.post(f'/api/projects/{pid}/proposals/{draft["id"]}/confirm',headers=headers,json={"expected_version":draft['version']});assert response.status_code==200
            before=client.get(f'/api/projects/{pid}',headers=headers).json();assert len(before['tasks'])==4
            steps.append('真实 TCP：创建→存原文→生成→确认→读取四项任务通过')
            response=client.get(f'/api/projects/{pid}');assert response.status_code==401
            steps.append('真实 TCP：无成员凭据被拒绝（401）')
            stop(process);process=None;process=start(env)
            response=client.get(f'/api/projects/{pid}',headers=headers);assert response.status_code==200
            after=response.json();assert before['tasks']==after['tasks'];assert before['events']==after['events'];assert before['sources']==after['sources']
            steps.append('真实停止并重启进程：原文、正式任务与审计完全保留')
        result={"success":True,"steps":steps,"database":"临时独立数据库，测试后清理；未操作 8886 主服务","real_model_tested":False}
        (out/'http-restart-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        for item in steps:print('PASS',item)
finally:
    stop(process)
