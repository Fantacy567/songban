"""Exercise real stdio MCP processes against the isolated local audit HTTP server."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('SONGBAN_QA_URL', 'http://127.0.0.1:8894')


def main():
    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client, tempfile.TemporaryDirectory() as tmp:
        marker = client.get('/api/audit-fixture').json()
        assert marker.get('isolated_audit') and marker.get('sms') == 'fixture'
        def api(method, path, token, body=None):
            response = client.request(method, path, headers={'Authorization': 'Bearer ' + token} if token else {}, json=body)
            assert response.status_code == 200, (path, response.status_code)
            return response.json()

        accounts = []
        for phone in ('18800008893', '18800008894'):
            accounts.append(api('POST', '/api/studio/login', '', {'phone': phone, 'password': 'materials-test-password'}))
        a, b = [account['token'] for account in accounts]
        team = api('POST', '/api/core/teams', a, {'name': '真实 MCP 进程闭环（合成数据）'})
        api('POST', '/api/core/join', b, {'code': team['code']})
        url = '/api/core/teams/' + team['id']
        snap = lambda: api('GET', url, a)
        api('PUT', url + '/direction', a, {'goal': '验证两个个人工具与团队同步', 'rules': '合成验收', 'expected_revision': snap()['revision']})
        connections = [api('POST', url + '/connections', token, {'label': '审计 MCP 子进程'}) for token in (a, b)]

        def mcp(index, name, arguments=None, expect_error=False):
            work = Path(tmp) / str(index)
            work.mkdir(exist_ok=True)
            env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', SONGBAN_URL=BASE, SONGBAN_TEAM_ID=team['id'], SONGBAN_TOKEN=connections[index]['token'], SONGBAN_PROJECT_ROOT=str(work), SONGBAN_CONFIG=str(work / 'absent.json'))
            requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}}, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments or {}}}]
            result = subprocess.run([sys.executable, str(ROOT / 'plugins/songban-team/bridge.py'), 'mcp'], input='\n'.join(json.dumps(r, ensure_ascii=False) for r in requests) + '\n', text=True, encoding='utf-8', capture_output=True, cwd=work, env=env, timeout=30)
            assert result.returncode == 0
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            assert len(responses[1]['result']['tools']) == 3
            answer = responses[2]['result']
            assert bool(answer.get('isError')) == expect_error
            text = answer['content'][0]['text']
            return text if expect_error else json.loads(text)

        sent = []
        for i in range(2):
            result = mcp(i, 'songban_sync_progress', {'event_id': 'audit-initial', 'tool': '真实 stdio MCP 测试', 'summary': '合成进展：准备接口与页面联调', 'origin': 'personal_agent'})
            sent.append(result['sent'])
        proposal = api('POST', url + '/review', a, {})
        no_auto_publish = snap()['plan_version'] == 0
        api('POST', url + '/proposals/' + proposal['proposal_id'] + '/confirm', a, {'expected_revision': proposal['base_revision']})
        tasks = [mcp(i, 'songban_get_my_tasks') for i in range(2)]
        for i in range(2):
            task = tasks[i]['tasks'][0]
            result = mcp(i, 'songban_sync_progress', {'event_id': 'audit-completed', 'tool': '真实 stdio MCP 测试', 'summary': '合成成果：已验证输入输出', 'origin': 'personal_agent', 'task_key': task['key'], 'plan_version': tasks[i]['plan_version'], 'status': 'reported_done', 'evidence': ['合成正常和错误输入的检查记录']})
            assert result['sent'] == 1
            current = snap()
            row = next(t for t in current['active_plan']['tasks'] if t['key'] == task['key'])
            api('POST', url + '/tasks/' + task['key'] + '/check', (a, b)[1 - i], {'expected_revision': current['revision'], 'plan_version': current['plan_version'], 'report_id': row['latest_report_id'], 'verdict': 'accepted', 'note': '合成测试同伴核对'})
        completed = snap()
        api('PATCH', url + '/connections/' + connections[0]['id'], a, {'action': 'revoke'})
        revoked = mcp(0, 'songban_get_team_context', expect_error=True)
        evidence = {'transport': 'real stdio subprocess + real loopback HTTP + SQLite', 'model': 'explicit fixture', 'sms': 'fixture; no actual SMS', 'initial_sent': sent, 'plan_not_auto_published': no_auto_publish, 'own_task_counts': [len(t['tasks']) for t in tasks], 'same_direction': tasks[0]['direction'] == tasks[1]['direction'], 'accepted': completed['workflow']['accepted_tasks'], 'all_checked': completed['workflow']['all_handoffs_checked'], 'revoked_connection_error': revoked, 'native_plugin_host_tested_by_this_probe': False}
        assert evidence['all_checked'] and evidence['same_direction'] and '401' in revoked
        output = Path(os.environ.get('SONGBAN_AUDIT_OUTPUT', str(ROOT / '.browser-cache/materials/fixes-20261031'))) / 'mcp-loop.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
