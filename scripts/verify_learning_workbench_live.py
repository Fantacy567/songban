"""Explicit, bounded live acceptance using synthetic identities and a private credential file.

Never run from CI or application startup. --allow-live is required. Each request is
recorded before dispatch; an existing output ledger prevents spending the cap again.
No production database or administrator settings are changed.
"""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCENARIOS = [
    ('ai-tools', '我第一次用AI，请给一只会潜水的小狐狸写三行角色介绍：名字、爱好、本领。'),
    ('ai-tools', '保留刚才的名字和爱好，把本领改成给海星讲笑话。请把完整卡片放在成果里。'),
    ('ai-tools', '我想让这个角色住进一座会飞的学校。给我三种不同的故事可能，我来选。'),
    ('imagination', '我喜欢猫和太空，还没想好做什么。陪我发散三种不同的想法，先不要让我填表。'),
    ('first-project', '我想做一个按钮，点了向小狐狸问好。请给最小网页代码，并告诉我怎样亲手检查。'),
    ('plugins', '我的小网页里重要的句子不容易找到。插件可以怎么帮忙？请给一个能理解的小例子。'),
    ('models', '两个AI回答不同，就一定有一个更聪明吗？我怎么比较，请不要编造你刚做了真实测试。'),
    ('api', '我想让自己的作品问AI一句话。用一个小例子解释请求和回应，密钥应该放在哪里？'),
    ('model-powered-app', '我想给小狐狸网页加一个聊天功能。可以怎样试不同模型？失败时让网页怎样回应？'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-live', action='store_true')
    parser.add_argument('--private-env', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-calls', type=int, default=10)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=len(SCENARIOS))
    args = parser.parse_args()
    if not args.allow_live or not 1 <= args.max_calls <= 10 or not 0 <= args.start < len(SCENARIOS) or not 1 <= args.count <= len(SCENARIOS):
        parser.error('Explicit live authorization and a bounded scenario range are required')
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('Store private acceptance evidence outside the repository')
    output.mkdir(parents=True, exist_ok=True)
    ledger_path = output / 'live-ledger.json'
    lock_path = output / 'live-ledger.lock'
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(lock)
    try:
        ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {
            'authorization': '2026-11-04: at most 10 requests, 800 output tokens each, fictional materials',
            'calls': []}

        def persist():
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')

        def calls_used():
            # Only a manually verified pre-dispatch failure may be excluded.
            # Timeouts and invalid provider replies always consume the allowance.
            return sum(not (c.get('state') == 'not_dispatched' and c.get('pre_dispatch_evidence'))
                       for c in ledger['calls'])

        from app.environment import load_env
        load_env(args.private_env.resolve(strict=True))
        from app.planner import builtin_model
        private = builtin_model()
        if not private.get('api_key') or private['base_url'] != 'https://api.deepseek.com':
            raise ValueError('Existing DeepSeek credentials unavailable')
        config = dict(enabled=True, base_url=private['base_url'], api_key=private['api_key'],
            model=private['model_id'], max_calls=args.max_calls, max_output_tokens=800,
            timeout_seconds=60, max_concurrency=1, revision=1)
        # The existing fixture blocks all network by default. Only the explicitly
        # authorized provider invocation below restores the original socket function.
        original_connect = socket.create_connection
        # Windows certificate initialization needs its OS paths even though the
        # synthetic fixture intentionally clears all application environment keys.
        runtime_env = {k: v for k, v in os.environ.items()
                       if k.upper() in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH')}
        from tests.test_unified_workbench_integration import UnifiedWorkbenchIntegrationTests
        from app.learning_workbench.model import invoke_live
        fixture = UnifiedWorkbenchIntegrationTests('runTest')
        fixture.setUp()
        try:
            def live_runner(payload):
                if calls_used() >= args.max_calls:
                    raise RuntimeError('Authorized call cap reached')
                entry = {'number': len(ledger['calls']) + 1,
                    'course_id': payload['teacher']['course_id'], 'max_output_tokens': payload['max_output_tokens'],
                    'state': 'dispatched', 'started_at': time.time()}
                ledger['calls'].append(entry)
                persist()
                try:
                    with patch('socket.create_connection', original_connect), patch.dict(os.environ, runtime_env):
                        result = invoke_live(payload, config=config)
                    entry.update(state='returned', elapsed_seconds=round(time.time()-entry['started_at'], 3),
                        actual_model=result.get('actual_model'), usage=result.get('usage'),
                        reply=result.get('reply'), artifact=result.get('artifact'))
                    return result
                except Exception as error:
                    entry.update(state='unconfirmed', error_class=type(error).__name__)
                    raise
                finally:
                    persist()

            app = fixture.factory(fixture.path, core_only=True,
                learning_settings=replace(fixture.settings, course_enabled=True),
                platform_settings=replace(fixture.platform_settings, demo_mode=False),
                learning_workbench_settings_provider=lambda con=None: dict(config),
                learning_workbench_runner=live_runner)
            fixture.app, fixture.service = app, app.state.learning_v2
            began = time.monotonic()
            fixture.service.clock = lambda: fixture.now[0] + time.monotonic() - began
            fixture.a = fixture.client()
            fixture.login(fixture.a, 'parent-a')
            fixture.enter(fixture.a, fixture.lid)
            checks = []
            for course, content in SCENARIOS[args.start:args.start+args.count]:
                if calls_used() >= args.max_calls:
                    break
                current = fixture.post('/learning-workbench/sessions', {'course_id': course})
                current = fixture.mutation(current, '/messages', content=content, mode='live')
                app.state.learning_workbench.worker_once()
                current = fixture.a.get('/api/platform/v1/learning-workbench/sessions/'+current['id']).json()
                message = current['messages'][-1]
                check = {'course_id': course, 'status': message['status'], 'actual_model': message['actual_model'],
                         'has_artifact': bool(message.get('artifact')), 'call_number': len(ledger['calls'])}
                checks.append(check)
                print(json.dumps(check, ensure_ascii=False), flush=True)
                if message['status'] != 'succeeded':
                    break
                if course == 'ai-tools' and message.get('artifact'):
                    candidate = message['artifact']
                    fixture.mutation(current, '/artifacts', title=candidate['title'], content=candidate['content'],
                                     source_message_id=message['id'])
            report = dict(calls_used=calls_used(), attempts=len(ledger['calls']), maximum_calls=args.max_calls,
                checks=checks, passed=len(checks)==len(SCENARIOS[args.start:args.start+args.count]) and all(c['status']=='succeeded' for c in checks),
                semantic_review='Required: read fictional replies; HTTP success is not teaching validation',
                production_data_changed=False)
            (output/f'results-{args.start}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k:v for k,v in report.items() if k != 'checks'}, ensure_ascii=False), flush=True)
            return 0 if report['passed'] else 1
        finally:
            fixture.doCleanups()
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('Live verification stopped (' + type(error).__name__ + '); inspect the redacted ledger.', file=sys.stderr)
        raise SystemExit(2)
