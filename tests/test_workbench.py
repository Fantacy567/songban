"""Isolated SQLite/API protocol tests; no paid model, SMS or manual database."""
import json
import re
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app, digest
from app.planner import PlannerError
from app.workbench_model import dump
from tests import test_team_core as core_fixture


def fixture(context):
    return {'text': '协议测试：先对照材料核实目标。', 'actions': [{'type': 'share_turn', 'label': '预览共享'}],
            'requested_model': 'protocol-fixture-request', 'actual_model': 'protocol-fixture-actual', 'mode': 'fixture'}


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        core_fixture.CoreTests.setUp(self)
        self.client.close()
        self.cfg2 = patch('app.workbench.team_model_config', return_value={'api_key': '', 'model_id': 'unconfigured'})
        self.cfg2.start()
        self.calls = []
        def model(context):
            self.calls.append(context)
            return fixture(context)
        self.app = create_app(self.path, core_only=True, workbench_model_runner=model)
        self.client = TestClient(self.app)
        self.counter = 0
        self.ws = self.new()

    def tearDown(self):
        self.cfg2.stop()
        core_fixture.CoreTests.tearDown(self)

    def sql(self, command, args=()):
        with closing(sqlite3.connect(self.path)) as con:
            con.row_factory = sqlite3.Row
            result = [dict(r) for r in con.execute(command, args)]
            con.commit()
            return result

    def key(self):
        self.counter += 1
        return 'request-' + str(self.counter)

    def new(self, team=None, actor='a', **extra):
        r = self.client.post('/api/workbench/sessions', headers=self.h(actor), json={'request_id': self.key(), 'title': '讨论', 'team_id': team, **extra})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['session']['id']

    def turn(self, ws=None, client=None, actor='a', **extra):
        return (client or self.client).post('/api/workbench/sessions/' + (ws or self.ws) + '/turns', headers=self.h(actor),
            json={'request_id': self.key(), 'text': '请理清目标', 'role_id': 'direction', 'source_ids': [], **extra})

    def history(self, ws=None, client=None, actor='a'):
        return (client or self.client).get('/api/workbench/sessions/' + (ws or self.ws), headers=self.h(actor))

    def share(self, mid, ws=None, client=None, actor='a', **extra):
        return (client or self.client).post('/api/workbench/sessions/' + (ws or self.ws) + '/share', headers=self.h(actor),
            json={'request_id': self.key(), 'message_id': mid, 'team_id': self.sid, 'summary': '我编辑的摘要', 'selected': True, **extra})

    def material(self, actor='a', team=None, content='已选择资料', parsed=True):
        r = self.client.get('/api/materials/space', params={'team_id': team or ''}, headers=self.h(actor))
        self.assertEqual(r.status_code, 200, r.text)
        base = '/api/materials/spaces/' + r.json()['id']
        r = self.client.post(base + '/sources', headers=self.h(actor), json={'request_id': self.key(), 'name': '测试材料', 'kind': 'text', 'content': content, 'nature': 'sample'})
        self.assertEqual(r.status_code, 200, r.text)
        ident = r.json()['source']['id']
        if parsed:
            revision = self.client.get(base, headers=self.h(actor)).json()['revision']
            r = self.client.post(base + '/sources/' + ident + '/parse', headers=self.h(actor), json={'expected_revision': revision})
            self.assertEqual(r.status_code, 200, r.text)
        return ident

    def test_personal_context_and_openapi_contract(self):
        r = self.client.get('/api/workbench/context', headers=self.h('a'))
        self.assertEqual(r.status_code, 200)
        value = r.json()
        self.assertIsNone(value['team'])
        self.assertIsNone(value['direction'])
        self.assertEqual(value['my_tasks'], [])
        self.assertEqual([x['id'] for x in value['roles']], ['materials', 'direction', 'next_step'])
        for path in ('/context', '/sessions', '/sessions/{sid}', '/sessions/{sid}/turns', '/sessions/{sid}/share', '/requests/{ident}'):
            self.assertIn('/api/workbench' + path, self.app.openapi()['paths'])

    def test_history_titles_use_first_question_and_rename_stays_private(self):
        first = self.new(title='新的项目讨论')
        empty = self.new(title='新的项目讨论')
        response = self.turn(ws=first, text='  校园失物\n如何核对认领人？  ')
        self.assertEqual(response.status_code, 200, response.text)
        rows = self.client.get('/api/workbench/sessions', headers=self.h('a')).json()['sessions']
        titles = {r['id']: r['title'] for r in rows}
        self.assertEqual(titles[first], '校园失物 如何核对认领人？')
        self.assertEqual(titles[empty], '未开始的讨论')
        path = '/api/workbench/sessions/' + first
        self.assertEqual(self.client.patch(path, headers=self.h('b'), json={'request_id': self.key(), 'title': '越权名称'}).status_code, 404)
        self.assertEqual(self.client.patch(path, headers=self.h('a'), json={'request_id': self.key(), 'title': '   '}).status_code, 422)
        command = {'request_id': self.key(), 'title': '认领流程与隐私'}
        renamed = self.client.patch(path, headers=self.h('a'), json=command)
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(self.client.patch(path, headers=self.h('a'), json=command).json(), renamed.json())
        self.assertEqual(self.client.patch(path, headers=self.h('a'), json=command | {'title':'冲突'}).status_code, 409)
        self.turn(ws=first, text='继续讨论')
        self.assertEqual(self.history(ws=first).json()['session']['title'], '认领流程与隐私')
        # An explicit rename also wins when it happens to match a default label.
        self.client.patch(path, headers=self.h('a'), json={'request_id': self.key(), 'title': '新的项目讨论'})
        self.assertEqual(self.history(ws=first).json()['session']['title'], '新的项目讨论')
        titles = {r['id']: r['title'] for r in self.client.get('/api/workbench/sessions', headers=self.h('a')).json()['sessions']}
        self.assertEqual(titles[first], '新的项目讨论')
        self.assertEqual(self.client.patch(path, headers=self.h('a'), json=command).json()['session']['title'], '新的项目讨论')
        foreign = self.client.get('/api/workbench/sessions', headers=self.h('b')).json()['sessions']
        self.assertNotIn(first, [row['id'] for row in foreign])

    def test_team_guidance_is_for_viewer_and_not_added_to_model_context(self):
        context = self.client.get('/api/workbench/context', params={'team_id': self.sid}, headers=self.h('a')).json()
        self.assertEqual(context['personal_session_count'], 1)
        self.assertIn('next_action', context['workflow'])
        other = self.client.get('/api/workbench/context', params={'team_id': self.sid}, headers=self.h('b')).json()
        self.assertEqual(other['personal_session_count'], 0)
        ws = self.new(team=self.sid)
        self.assertEqual(self.turn(ws=ws).status_code, 200)
        self.assertNotIn('workflow', self.calls[-1])
        self.assertNotIn('personal_session_count', self.calls[-1])

    def test_create_idempotent_conflict_preserves_history(self):
        body = {'request_id': 'stable-create', 'title': '第一次', 'team_id': None}
        a = self.client.post('/api/workbench/sessions', headers=self.h('a'), json=body)
        b = self.client.post('/api/workbench/sessions', headers=self.h('a'), json=body)
        self.assertEqual(a.json(), b.json())
        conflict = self.client.post('/api/workbench/sessions', headers=self.h('a'), json=body | {'title': '改变'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.turn().status_code, 200)
        self.new()
        self.assertEqual(len(self.history().json()['messages']), 2)

    def test_owner_team_and_connector_isolation(self):
        team_ws = self.new(team=self.sid)
        self.assertEqual(self.history(actor='b').status_code, 404)
        self.assertEqual(self.turn(actor='b').status_code, 404)
        self.assertEqual(self.history(team_ws, actor='b').status_code, 404)
        self.assertEqual(self.client.get('/api/workbench/context', params={'team_id': self.sid}, headers=self.h('c')).status_code, 403)
        connection = self.client.post(self.base + '/connections', headers=self.h('a'), json={'label': '测试'}).json()
        header = {'Authorization': 'Bearer ' + connection['token']}
        self.assertEqual(self.client.get('/api/workbench/sessions', headers=header).status_code, 401)
        self.sql('DELETE FROM squad_members WHERE squad_id=? AND user_id=?', (self.sid, 'a'))
        self.assertEqual(self.history(team_ws).status_code, 403)
        self.assertEqual(self.history().status_code, 200)

    def test_catalog_and_selected_materials_only(self):
        mine = self.material()
        hidden = self.material(actor='b', content='其他人的私有内容')
        shared = self.material(actor='b', team=self.sid, content='共享材料')
        unparsed = self.material(content='尚未解析', parsed=False)
        team_ws = self.new(team=self.sid)
        context = self.client.get('/api/workbench/context', params={'team_id': self.sid}, headers=self.h('a')).json()
        self.assertEqual({r['id'] for r in context['sources']}, {mine, shared})
        self.assertTrue(context['team']['is_captain'])
        self.assertEqual(self.turn(ws=team_ws, source_ids=[mine, mine]).status_code, 200)
        sent = self.calls[-1]
        self.assertEqual([r['id'] for r in sent['sources']], [mine])
        self.assertEqual(sent['sources'][0]['nature'], 'sample')
        for forbidden in (hidden, shared, unparsed):
            self.assertEqual(self.turn(source_ids=[forbidden]).status_code, 403)
        self.assertNotIn('members', sent)
        self.assertNotIn('reports', sent)

    def test_my_confirmed_tasks_only(self):
        plan = {'tasks': [{'key': 'T1', 'title': '我的正式任务', 'owner_id': 'a', 'acceptance': '核对', 'depends_on': []}, {'key': 'T2', 'title': '其他人任务内容', 'owner_id': 'b', 'acceptance': '核对', 'depends_on': []}]}
        self.sql('UPDATE core_settings SET active_plan=?,plan_version=1 WHERE squad_id=?', (json.dumps(plan), self.sid))
        context = self.client.get('/api/workbench/context', params={'team_id': self.sid}, headers=self.h('a')).json()
        self.assertEqual([t['key'] for t in context['my_tasks']], ['T1'])

    def test_turn_idempotency_and_provenance(self):
        a = self.turn(request_id='stable-turn')
        self.assertEqual(a.status_code, 200, a.text)
        b = self.turn(request_id='stable-turn')
        self.assertEqual(a.json(), b.json())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.turn(request_id='stable-turn', text='不一样').status_code, 409)
        value = a.json()
        self.assertEqual(value['message']['requested_model'], 'protocol-fixture-request')
        self.assertEqual(value['message']['actual_model'], 'protocol-fixture-actual')
        self.assertEqual(value['message']['mode'], 'fixture')
        self.assertIsNone(self.history().json()['messages'][0]['actual_model'])
        rid = value['request']['id']
        self.assertEqual(self.client.get('/api/workbench/requests/' + rid, headers=self.h('a')).json(), value)
        self.assertEqual(self.client.get('/api/workbench/requests/' + rid, headers=self.h('b')).status_code, 404)

    def test_validation(self):
        for extra in ({'text': '  '}, {'role_id': 'admin'}, {'source_ids': [str(n) for n in range(11)]}, {'request_id': 'short'}, {'text': 'x' * 8001}, {'user_id': 'b'}):
            self.assertEqual(self.turn(**extra).status_code, 422, extra)
        self.assertEqual(len(self.calls), 0)

    def test_actions_sanitized_and_member_review_removed(self):
        actions = [{'type': 'execute', 'label': '执行', 'code': 'x'}, {'type': 'open_page', 'label': '坏网址', 'page': 'https://example.com'},
                   {'type': 'open_page', 'label': '任务', 'page': 'tasks', 'url': 'https://evil.example'}, {'type': 'request_team_review', 'label': '统筹'},
                   {'type': 'prepare_direction', 'label': '方向', 'fields': {'goal': '小目标', 'deadline': '2026-11-02', 'admin': 'true'}},
                   {'type': 'share_turn', 'label': '分享', 'automatic': True}]
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=lambda c: fixture(c) | {'actions': actions})) as client:
            result = self.turn(client=client).json()['message']['actions']
            self.assertEqual([a['type'] for a in result], ['open_page', 'prepare_direction', 'share_turn'])
            self.assertNotIn('url', result[0])
            self.assertEqual(result[1]['fields'], {'goal': '小目标'})
            team_ws = self.new(team=self.sid)
            result = self.turn(ws=team_ws, client=client).json()['message']['actions']
            self.assertIn('request_team_review', [a['type'] for a in result])

    def test_parallel_same_session_and_same_request(self):
        started, release = threading.Event(), threading.Event()
        calls = []
        def slow(c):
            calls.append(c); started.set(); release.wait(5)
            return fixture(c)
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=slow)) as client, ThreadPoolExecutor() as pool:
            future = pool.submit(self.turn, client=client, request_id='running-request')
            self.assertTrue(started.wait(5))
            # A second app registration must not recover a live lease as unknown.
            with TestClient(create_app(self.path, core_only=True, workbench_model_runner=fixture)) as other:
                duplicate = self.turn(client=other, request_id='running-request')
                self.assertEqual(duplicate.status_code, 200)
                self.assertEqual(duplicate.json()['request']['status'], 'running')
                self.assertEqual(self.turn(client=other).json()['error']['code'], 'turn_in_progress')
            release.set()
            self.assertEqual(future.result().status_code, 200)
        self.assertEqual(len(calls), 1)

    def test_global_concurrency_limit_across_apps(self):
        gate, release = threading.Barrier(3), threading.Event()
        def slow(c):
            gate.wait(timeout=5); release.wait(5); return fixture(c)
        other_ws, third_ws = self.new(), self.new()
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=slow)) as client, ThreadPoolExecutor() as pool:
            first = pool.submit(self.turn, client=client)
            second = pool.submit(self.turn, ws=other_ws, client=client)
            gate.wait(timeout=5)
            with TestClient(create_app(self.path, core_only=True, workbench_model_runner=fixture)) as other:
                self.assertEqual(self.turn(ws=third_ws, client=other).status_code, 429)
            release.set()
            self.assertEqual(first.result().status_code, 200)
            self.assertEqual(second.result().status_code, 200)

    def test_timeout_unknown_no_replay_and_explicit_new_attempt(self):
        calls = []
        def timeout(c):
            calls.append(c); raise TimeoutError('test only')
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=timeout)) as client:
            self.assertEqual(self.turn(client=client, request_id='timeout-request').status_code, 504)
            repeat = self.turn(client=client, request_id='timeout-request')
            self.assertEqual(repeat.status_code, 200)
            self.assertEqual(repeat.json()['request']['status'], 'unknown')
            self.assertIsNone(repeat.json()['message'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.turn().status_code, 200)
        self.assertEqual(len(self.history().json()['messages']), 3)

    def test_restart_and_lease_expiry_do_not_replay(self):
        result = self.turn().json()
        ident = result['request']['id']
        self.sql("UPDATE workbench_requests SET status='running',message_id=NULL,lease_until='2000-01-01T00:00:00+00:00' WHERE id=?", (ident,))
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=fixture)) as client:
            request = client.get('/api/workbench/requests/' + ident, headers=self.h('a')).json()['request']
            self.assertEqual(request['status'], 'unknown')
            self.assertEqual(request['error']['code'], 'request_expired')
        self.assertEqual(len(self.calls), 1)

    def test_expired_pending_never_calls_runner_even_after_recovery(self):
        from app import main
        real_register = main.register_workbench
        calls = []
        for recovered in (False, True):
            with self.subTest(recovered=recovered):
                marker = 'preflight-expired-' + str(recovered)
                def register(*args):
                    original_db = args[1]
                    @contextmanager
                    def intercepted(write=False):
                        # Simulate another worker's expiry recovery after the input
                        # transaction commits, before the provider claim transaction.
                        with original_db(write) as con:
                            if write and con.execute("SELECT 1 FROM sqlite_master WHERE name='workbench_requests'").fetchone():
                                con.execute("UPDATE workbench_requests SET lease_until='2000-01-01T00:00:00+00:00',status=? WHERE request_id=? AND status='pending'", ('unknown' if recovered else 'pending', marker))
                            yield con
                    return real_register(args[0], intercepted, *args[2:])
                with patch('app.main.register_workbench', register):
                    app = create_app(self.path, core_only=True, workbench_model_runner=lambda c: calls.append(c) or fixture(c))
                with TestClient(app) as client:
                    result = self.turn(client=client, request_id=marker)
                    self.assertEqual(result.status_code, 409, result.text)
                    self.assertEqual(result.json()['error']['code'], 'request_expired')
                request = self.sql('SELECT status FROM workbench_requests WHERE request_id=?', (marker,))[0]
                self.assertEqual(request['status'], 'unknown')
        self.assertEqual(calls, [])

    def test_late_response_after_expiry_is_never_saved(self):
        def expired(c):
            self.sql("UPDATE workbench_requests SET lease_until='2000-01-01T00:00:00+00:00' WHERE status='running'")
            # GET performs recovery before the runner returns.
            self.assertEqual(self.history().json()['requests'][0]['status'], 'unknown')
            return fixture(c)
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=expired)) as client:
            self.assertEqual(self.turn(client=client).status_code, 409)
        history = self.history().json()
        self.assertEqual(history['requests'][0]['status'], 'unknown')
        self.assertEqual([m['role'] for m in history['messages']], ['user'])

    def test_source_change_and_token_revocation_discard_late_response(self):
        for scenario in ('source_version', 'token', 'membership', 'direction'):
            with self.subTest(scenario=scenario):
                src = self.material(content='来源 ' + scenario)
                team_ws = self.new(team=self.sid)
                def changing(c):
                    if scenario == 'source_version':
                        self.sql('UPDATE materials_sources SET version=version+1 WHERE id=?', (src,))
                    elif scenario == 'token':
                        self.sql('UPDATE people SET token_hash=? WHERE id=?', (digest('replacement-token'), 'a'))
                    elif scenario == 'membership':
                        self.sql('DELETE FROM squad_members WHERE squad_id=? AND user_id=?', (self.sid, 'a'))
                    else:
                        self.sql("UPDATE core_settings SET direction=? WHERE squad_id=?", (json.dumps({'goal': 'new'}), self.sid))
                    return fixture(c)
                with TestClient(create_app(self.path, core_only=True, workbench_model_runner=changing)) as client:
                    r = self.turn(ws=team_ws, client=client, source_ids=[src])
                    self.assertIn(r.status_code, (401, 403, 409), r.text)
                self.assertFalse(self.sql("SELECT * FROM workbench_messages WHERE session_id=? AND role='assistant'", (team_ws,)))
                self.sql('UPDATE people SET token_hash=? WHERE id=?', (digest('test-token-a'), 'a'))
                if scenario == 'membership':
                    self.sql("INSERT INTO squad_members(squad_id,user_id,role) VALUES(?,?,?)", (self.sid, 'a', '队长'))

    def test_cached_response_and_history_cannot_reuse_revoked_source(self):
        src = self.material()
        result = self.turn(source_ids=[src], request_id='source-request').json()
        self.sql("UPDATE materials_sources SET status='failed' WHERE id=?", (src,))
        self.assertEqual(self.turn(source_ids=[src], request_id='source-request').status_code, 403)
        history = self.history().json()
        self.assertEqual([m['role'] for m in history['messages']], ['user'])
        self.assertEqual(history['requests'][0]['status'], 'failed')
        self.assertEqual(self.share(result['message']['id']).status_code, 403)

    def test_history_selection_and_sensitive_context(self):
        src = self.material(content='PRIVATE_SOURCE_CONTENT\nAPI_KEY=sk-123456789abcdefgh\n手机号：18000000000')
        self.assertEqual(self.turn(source_ids=[src]).status_code, 200)
        self.assertNotIn('sk-123456789abcdefgh', json.dumps(self.calls[-1]))
        self.assertNotIn('18000000000', json.dumps(self.calls[-1]))
        self.assertEqual(self.turn().status_code, 200)
        self.assertEqual(self.calls[-1]['history'], [])
        self.assertTrue(self.calls[-1]['coverage']['history_limited'])

    def test_phone_shaped_source_ids_and_real_sha256_survive_api_and_restart(self):
        source_id = 'a13800000000f' + 'a' * 19
        segment_id = 'b13900000000e'
        original = self.material(content='正文联系13800000000，API_KEY=sk-testsecret123456789。' + '很长的材料。' * 5000)
        self.sql('UPDATE materials_sources SET id=?,version=? WHERE id=?', (source_id, 13800000000, original))
        row = self.sql('''SELECT s.id,s.version,s.status,s.metadata,s.segments,s.warnings,p.team_id,p.owner_id
          FROM materials_sources s JOIN materials_spaces p ON p.id=s.space_id WHERE s.id=?''', (source_id,))[0]
        segments = json.loads(row['segments'])
        segments[0]['id'] = segment_id
        row['segments'] = dump(segments)
        row['status'] = 'partial'
        row['warnings'] = dump(['OCR待核对，联系13800000000'])
        metadata = json.loads(row['metadata'])
        # Find a genuine SHA-256 with a phone-shaped decimal run. This tests the
        # actual fingerprint path, without mocking digest or permission checks.
        phone_run = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
        for suffix in range(10000):
            metadata['name'] = '资料联系13800000000，版本样本' + str(suffix)
            row['metadata'] = dump(metadata)
            expected_hash = digest(dump(row))
            if phone_run.search(expected_hash):
                break
        else:
            self.fail('没有找到测试用十进制 SHA-256 片段')
        self.sql('UPDATE materials_sources SET metadata=?,segments=?,warnings=?,status=? WHERE id=?',
                 (row['metadata'], row['segments'], row['warnings'], row['status'], source_id))
        catalog = self.client.get('/api/workbench/context', headers=self.h('a')).json()['sources']
        self.assertEqual(catalog[0]['id'], source_id)
        self.assertNotIn('13800000000', catalog[0]['name'])
        turn_body = {'source_ids': [source_id], 'request_id': 'phone-shaped-source', 'text': '示例联系号码13800000000'}
        result = self.turn(**turn_body)
        self.assertEqual(result.status_code, 200, result.text)
        value = result.json()
        ref = value['message']['sources'][0]
        self.assertEqual(ref['id'], source_id)
        self.assertEqual(ref['fingerprint'], expected_hash)
        self.assertEqual(ref['version'], 13800000000)
        self.assertTrue(ref['truncated'])
        self.assertEqual(value['message']['coverage']['truncated_source_ids'], [source_id])
        self.assertNotIn('13800000000', ref['warnings'][0])
        sent = self.calls[-1]
        self.assertEqual(sent['sources'][0]['id'], source_id)
        self.assertEqual(sent['sources'][0]['segments'][0]['id'], segment_id)
        self.assertEqual(sent['coverage']['truncated_source_ids'], [source_id])
        self.assertNotIn('13800000000', sent['text'])
        self.assertNotIn('13800000000', sent['sources'][0]['segments'][0]['text'])
        self.assertNotIn('sk-testsecret123456789', sent['sources'][0]['segments'][0]['text'])
        rid = value['request']['id']
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=fixture)) as restarted:
            recovered = restarted.get('/api/workbench/requests/' + rid, headers=self.h('a'))
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json(), value)
            self.assertEqual(self.history(client=restarted).json()['messages'][-1]['sources'][0]['fingerprint'], expected_hash)
            self.assertEqual(self.turn(client=restarted, **turn_body).json(), value)
        self.assertEqual(len(self.calls), 1)

    def test_bounded_materials_include_truncation_warning(self):
        src = self.material(content='长材料。' * 7000)
        self.sql("UPDATE materials_sources SET status='partial',warnings=? WHERE id=?", (json.dumps(['OCR测试警告：请核对']), src))
        result = self.turn(source_ids=[src])
        self.assertEqual(result.status_code, 200)
        returned_source = result.json()['message']['sources'][0]
        self.assertTrue(returned_source['truncated'])
        self.assertEqual(returned_source['status'], 'partial')
        self.assertEqual(returned_source['warnings'], ['OCR测试警告：请核对'])
        self.assertIn(src, result.json()['message']['coverage']['truncated_source_ids'])
        self.assertEqual(self.history().json()['messages'][-1]['sources'], result.json()['message']['sources'])
        sent = self.calls[-1]
        self.assertIn(src, sent['coverage']['truncated_source_ids'])
        self.assertLessEqual(sum(len(seg['text']) for s in sent['sources'] for seg in s['segments']), 24000)

    def test_share_explicit_true_source_round_and_no_analysis(self):
        result = self.turn().json()
        mid = result['message']['id']
        self.sql('UPDATE core_settings SET auto_review=1 WHERE squad_id=?', (self.sid,))
        self.assertEqual(self.share(mid, selected=False).status_code, 422)
        self.assertEqual(self.share(mid, actor='b').status_code, 404)
        self.assertEqual(self.share(mid, model_name='forged').status_code, 422)
        first = self.share(mid, request_id='stable-share')
        self.assertEqual(first.status_code, 200, first.text)
        second = self.share(mid, request_id='stable-share')
        self.assertEqual(first.json()['note_id'], second.json()['note_id'])
        self.assertTrue(second.json()['duplicate'])
        self.assertFalse(first.json()['analysis_triggered'])
        self.assertEqual(self.share(mid, request_id='stable-share', summary='different').status_code, 409)
        report = json.loads(self.sql('SELECT body FROM core_reports')[0]['body'])
        self.assertEqual(report['user_message'], '请理清目标')
        self.assertEqual(report['model_name'], 'protocol-fixture-actual')
        self.assertEqual(report['tool'], '松伴项目工作台')
        self.assertTrue(report['capture_only'])
        self.assertIn('fixture', report['excerpt'])
        self.assertEqual(len(self.sql('SELECT * FROM library_notes')), 1)
        self.assertEqual(len(self.sql('SELECT * FROM core_proposals')), 0)

    def test_team_session_cannot_share_to_different_team(self):
        other = self.client.post('/api/core/teams', headers=self.h('a'), json={'name': '另一个团队'}).json()['id']
        ws = self.new(team=self.sid)
        result = self.turn(ws=ws).json()
        self.assertEqual(self.share(result['message']['id'], ws=ws, team_id=other).status_code, 403)

    def test_share_does_not_reintroduce_private_details_removed_from_summary(self):
        marker = 'PRIVATE_MARKER_REMOVED_BY_USER'
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=lambda c: fixture(c) | {'text': '可分享建议。私人细节：' + marker})) as client:
            result = self.turn(client=client)
            self.assertEqual(result.status_code, 200)
            mid = result.json()['message']['id']
            shared = self.share(mid, client=client, summary='我仅选择分享建议。')
            self.assertEqual(shared.status_code, 200, shared.text)
        self.assertNotIn(marker, json.dumps(self.sql('SELECT * FROM core_reports')))
        self.assertNotIn(marker, json.dumps(self.sql('SELECT * FROM library_notes')))
        self.assertIn(marker, self.history().json()['messages'][-1]['text'])

    def test_share_crash_after_archive_is_recoverable(self):
        captured = {}
        from app import main
        real_register = main.register_workbench
        def register(*args):
            captured['core'] = args[6]
            return real_register(*args)
        with patch('app.main.register_workbench', register):
            app = create_app(self.path, core_only=True, workbench_model_runner=fixture)
        core = captured['core']; original = core['save_report']; calls = []
        def crash(*args, **kwargs):
            calls.append(1); original(*args, **kwargs); raise RuntimeError('crash after core commit')
        mid = self.turn().json()['message']['id']
        with TestClient(app) as client:
            core['save_report'] = crash
            self.assertEqual(self.share(mid, client=client, request_id='recover-share').status_code, 503)
            self.assertEqual(len(self.history().json()['messages']), 2)
            core['save_report'] = original
            recovered = self.share(mid, client=client, request_id='recover-share')
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertTrue(recovered.json()['duplicate'])
        self.assertEqual(len(self.sql('SELECT * FROM core_reports')), 1)
        self.assertEqual(len(self.sql('SELECT * FROM library_notes')), 1)

    def test_concurrent_share_creates_one_note(self):
        mid = self.turn().json()['message']['id']
        with ThreadPoolExecutor() as pool:
            tasks = [pool.submit(self.share, mid, request_id='parallel-share') for _ in range(3)]
            results = [f.result() for f in tasks]
        self.assertTrue(all(r.status_code == 200 for r in results), [r.text for r in results])
        self.assertEqual(len({r.json()['note_id'] for r in results}), 1)
        self.assertEqual(len(self.sql('SELECT * FROM core_reports')), 1)

    def test_missing_model_and_invalid_fixture_are_not_success(self):
        with patch('app.workbench_model.team_model_config', return_value={'api_key': '', 'model_id': 'unconfigured'}):
            with TestClient(create_app(self.path, core_only=True)) as client:
                r = self.turn(client=client)
                self.assertEqual(r.status_code, 503)
                self.assertEqual(r.json()['error']['code'], 'model_not_configured')
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=lambda c: {'text': 'unlabelled'})) as client:
            self.assertEqual(self.turn(client=client).status_code, 502)
        history = self.history().json()
        self.assertEqual([r['status'] for r in history['requests']], ['failed', 'failed'])
        self.assertEqual([m['role'] for m in history['messages']], ['user', 'user'])

    def test_actual_model_unknown_remains_null(self):
        with TestClient(create_app(self.path, core_only=True, workbench_model_runner=lambda c: fixture(c) | {'actual_model': None})) as client:
            result = self.turn(client=client)
            self.assertIsNone(result.json()['message']['actual_model'])
            mid = result.json()['message']['id']
            self.assertEqual(self.share(mid, client=client).status_code, 200)
        report = json.loads(self.sql('SELECT body FROM core_reports')[0]['body'])
        self.assertEqual(report['model_name'], '')

    def test_user_rate_limit(self):
        with patch('app.workbench.MAX_PER_MINUTE', 2):
            self.assertEqual(self.turn().status_code, 200)
            self.assertEqual(self.turn().status_code, 200)
            self.assertEqual(self.turn().status_code, 429)


if __name__ == '__main__':
    unittest.main()
