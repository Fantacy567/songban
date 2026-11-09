# Copyright (c) 2026 2292576833. Upstream retains its MIT license.
"""Real Docker/Harness tool round-trip with an in-memory synthetic provider.

No paid endpoint, real credentials, project database or child records are loaded.
There is deliberately no host execution fallback when Docker is unavailable.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.creative_studio.harness import HarnessRunner, REVISION, CONTRACT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine', help='Operator-selected Docker-compatible executable (e.g. podman)')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'revision': REVISION, 'contract': CONTRACT, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'kind': 'real-container-with-synthetic-provider', 'real_container': False,
              'real_agent_runtime': False, 'real_model_calls': 0, 'passed': False}
    calls, received, requests = [], [], []
    expected = 'document.body.dataset.offlineProbe = "passed";'

    class ObservedRunner(HarnessRunner):
        container_name = None
        def command(self, name):
            self.container_name = name
            return super().command(name)

    def provider(request):
        assert str(request.url) == 'https://api.deepseek.com/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'synthetic-model'
        requests.append(body)
        index = len(requests)
        assert index <= 3, 'Unexpected retry or extra model request'
        names = {tool['function']['name'] for tool in body.get('tools', [])}
        assert names == {'read', 'write', 'edit'}, names
        if index == 1:
            info = json.loads(subprocess.check_output([runner.docker, 'inspect', runner.container_name], timeout=5))[0]
            host = info['HostConfig']
            assert host['NetworkMode'] == 'none' and host['ReadonlyRootfs']
            assert info['Config']['User'] == '1000:1000'
            assert 'ALL' in host['CapDrop'] and 'no-new-privileges' in host['SecurityOpt']
            assert not any(m['Type'] in ('bind','volume') for m in info['Mounts'])
            report['isolation'] = {'network':'none','readonly_root':True,'user':'1000:1000','host_mounts':False}
        if index == 2:
            assert any(m.get('role') == 'tool' and 'Only the three /work project files' in str(m.get('content')) for m in body['messages']), 'Guard denial missing from real tool transcript'
        if index < 3:
            file_path = '/tmp/songban.patch.yml' if index == 1 else '/work/script.js'
            delta = {'role':'assistant','content':None,'tool_calls':[{'index':0,'id':f'synthetic-{index}',
                'type':'function','function':{'name':'write','arguments':json.dumps({'file_path':file_path,'content':'denied fixture' if index==1 else expected})}}]}
            finish = 'tool_calls'
        else:
            delta = {'role':'assistant','content':'已修改 script.js。请在预览中自行观察。'}
            finish = 'stop'
        base = {'id':f'synthetic-{index}','object':'chat.completion.chunk','created':0,'model':'synthetic-model'}
        if body.get('stream'):
            chunks = [base | {'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                      base | {'choices':[{'index':0,'delta':{},'finish_reason':finish}], 'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}]
            text = ''.join('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n'
            return httpx.Response(200, text=text, headers={'content-type':'text/event-stream'})
        return httpx.Response(200, json=base | {'object':'chat.completion', 'choices':[{'index':0,'message':delta,'finish_reason':finish}]})

    runner = ObservedRunner(docker=args.engine, transport=httpx.MockTransport(provider))
    try:
        if not runner.available():
            report['blocked_reason'] = 'Docker engine or pinned image with current worker contract is unavailable; no host fallback.'
            return 2
        def reserve():
            assert len(calls) < 3
            calls.append(str(len(calls)+1))
            return calls[-1]
        payload = {'files':[{'path':'index.html','content':'<p>Offline fixture</p>'},
                            {'path':'style.css','content':''},{'path':'script.js','content':''}],
                   'text':'Perform the synthetic fixture only.', 'idea':'Offline fixture', 'history':[],
                   'teaching':'Use only the three project files. No network or shell.', 'curriculum':{},
                   'config':{'model':'synthetic-model','api_key':'synthetic-not-a-secret','max_output_tokens':800,'timeout_seconds':30},
                   'reserve_call':reserve,'record_call':lambda cid,usage:received.append(cid), 'deadline_seconds':100}
        result = runner(payload)
        assert next(f['content'] for f in result['files'] if f['path']=='script.js') == expected
        assert len(requests) == 3 and calls == received
        assert result['actual_model'] == 'synthetic-model'
        assert '已修改' in result['text']
        report.update(passed=True,real_container=True,real_agent_runtime=True,synthetic_requests=len(requests),
                      checks=['real SDK handshake','real pi-ai stream parsing','guard denied non-project path',
                              'real file write and collection','container flags inspected','no paid transport'])
        return 0
    except Exception as error:
        # Fixture inputs are synthetic, but avoid copying arbitrary tool or
        # Docker diagnostics into a report that may later be shared.
        report['error_type'] = type(error).__name__
        raise
    finally:
        if runner.container_name:
            check = subprocess.run([runner.docker,'container','ls','-aq','--filter','name=^/'+runner.container_name+'$'],capture_output=True,timeout=5)
            report['container_removed'] = check.returncode == 0 and not check.stdout.strip()
            if check.returncode == 0 and check.stdout.strip():
                subprocess.run([runner.docker,'rm','-f',runner.container_name],capture_output=True,timeout=10,check=True)
            if not report['container_removed']:
                report['passed'] = False
        (args.output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if runner.container_name and not report['container_removed']:
            raise RuntimeError('Container cleanup did not pass verification')


if __name__ == '__main__':
    raise SystemExit(main())
