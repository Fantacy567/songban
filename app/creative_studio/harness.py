# Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
"""Pinned source Harness in a credential-free, network-free Linux container.

Only bounded chat requests cross stdio; the host alone supplies authentication.
No user-controlled argv, paths, URL, mounts or environment are accepted.
"""
import json
import asyncio
import os
import queue
import shutil
import subprocess
import threading
import time
from app.learning_v2.protocol import canonical

REVISION='ce7073d51254c26cd63b22a60835b8f948deb447'
CONTRACT='2026-11-03-files-v1'
IMAGE='songban-harness:'+REVISION[:12]

class HarnessRunner:
    def __init__(self, *, docker=None, image=IMAGE, transport=None):
        self.docker=docker or shutil.which('docker')
        # Operator-configured image, never derived from browser/config content.
        self.image=image
        self.transport=transport
        self._checked=0; self._ready=False

    def available(self):
        if not self.docker: return False
        if time.monotonic()-self._checked < 15: return self._ready
        try:
            r=subprocess.run([self.docker,'image','inspect',self.image,'--format','{{index .Config.Labels "org.opencontainers.image.revision"}}:{{index .Config.Labels "org.songban.harness.contract"}}'],capture_output=True,timeout=4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self._ready=r.returncode==0 and r.stdout.decode().strip()==REVISION+':'+CONTRACT
        except (OSError,subprocess.TimeoutExpired): self._ready=False
        self._checked=time.monotonic()
        return self._ready

    def command(self, name):
        return [self.docker,'run','--rm','-i','--name',name,'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--pids-limit','96','--memory','768m','--cpus','1',
            '--user','1000:1000','--tmpfs','/tmp:rw,noexec,nosuid,size=128m,uid=1000,gid=1000',
            '--tmpfs','/work:rw,noexec,nosuid,size=16m,uid=1000,gid=1000',self.image]

    def relay(self, frame, payload):
        import httpx
        c=payload['config']
        if frame.get('path') not in ('/v1/chat/completions','/chat/completions') or frame.get('method')!='POST':
            raise ValueError('Only model inference can leave the container')
        body=frame.get('body')
        if not isinstance(body,dict) or len(canonical(body).encode())>180000:
            raise ValueError('Model request exceeds limit')
        # No endpoint/header/key from the container is ever honored.
        body['model']=c['model']; body['max_tokens']=min(4096,int(c.get('max_output_tokens',800)))
        body.pop('max_completion_tokens',None)
        remaining=payload.get('absolute_deadline',time.monotonic()+120)-time.monotonic()
        call_timeout=min(120,int(c.get('timeout_seconds',60)),remaining)
        if call_timeout<=0: raise TimeoutError('Harness deadline before model dispatch')
        cid=payload['reserve_call']()  # durable before any network I/O
        async def consume():
            async with httpx.AsyncClient(timeout=call_timeout,follow_redirects=False,trust_env=False,transport=self.transport) as client:
                async with client.stream('POST','https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+c['api_key']},json=body) as response:
                    parts=[]; size=0
                    async for block in response.aiter_bytes():
                        size+=len(block)
                        if size>2_000_000: raise ValueError('Model response exceeds limit')
                        parts.append(block)
                    # Never echo provider credential errors into child logs / UI.
                    if response.status_code!=200: raise RuntimeError('Provider did not complete')
                    return b''.join(parts).decode('utf-8')
        async def bounded():
            # Total deadline includes active streaming, not only socket idle time.
            return await asyncio.wait_for(consume(),timeout=call_timeout)
        text=asyncio.run(bounded())
        usage=None; actual_model=None
        for line in text.splitlines():
            raw=line[6:] if line.startswith('data: ') else line
            if not raw or raw=='[DONE]': continue
            try:
                value=json.loads(raw)
                if isinstance(value,dict):
                    usage=value.get('usage') or usage; actual_model=value.get('model') or actual_model
            except ValueError: pass
        payload['record_call'](cid,{'usage':usage,'actual_model':actual_model})
        return {'type':'model_response','id':frame['id'],'status':200,'content_type':'text/event-stream' if body.get('stream') else 'application/json','body':text,'actual_model':actual_model}

    def __call__(self,payload):
        if not self.available(): raise RuntimeError('Isolated Harness is unavailable')
        import secrets
        name='songban-studio-'+secrets.token_hex(8)
        proc=subprocess.Popen(self.command(name),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        inbox=queue.Queue(maxsize=64)
        def read():
            try:
                while True:
                    line=proc.stdout.readline(2_500_001)
                    if not line: break
                    if len(line)>2_500_000: break
                    inbox.put(line,timeout=2)
            except Exception: pass
            finally:
                try: inbox.put(None,timeout=1)
                except queue.Full: pass
        thread=threading.Thread(target=read,daemon=True); thread.start()
        def send(value):
            proc.stdin.write(canonical(value)+'\n'); proc.stdin.flush()
        c=payload['config']; actual_model=None
        try:
            send({'type':'start','input':{k:payload[k] for k in ('files','text','idea','history','teaching','curriculum')},
                  'model':c['model'],'max_tokens':min(4096,int(c.get('max_output_tokens',800)))})
            deadline=time.monotonic()+payload.get('deadline_seconds',230)
            payload=payload | {'absolute_deadline':deadline}
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0: raise TimeoutError('Harness deadline')
                line=inbox.get(timeout=remaining)
                if line is None: raise RuntimeError('Harness exited before a result')
                frame=json.loads(line)
                if frame.get('type')=='model_request':
                    result=self.relay(frame,payload); actual_model=result.pop('actual_model',None) or actual_model; send(result)
                elif frame.get('type')=='result':
                    # Pinned SDK returns TurnEndReason.kind (e.g. max-tokens,
                    # blocked or interrupted), not provider finish_reason values.
                    # Only a positively completed turn may persist AI files.
                    if frame.get('finish_reason') != 'completed': raise RuntimeError('Harness turn incomplete')
                    return {'files':frame['files'],'text':frame['text'],'actual_model':actual_model}
                elif frame.get('type')=='failure': raise RuntimeError('Harness rejected work')
        finally:
            # Terminating docker CLI alone does not prove container termination.
            try:
                cleanup=subprocess.run([self.docker,'rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                # A completed SDK turn is not a successful isolated job while
                # its container may still be alive. Keep diagnostics private.
                if cleanup.returncode != 0:
                    raise RuntimeError('Harness container cleanup was not confirmed')
            finally:
                if proc.poll() is None: proc.kill()
                proc.wait(timeout=10)
                proc.stdin.close(); proc.stdout.close()
