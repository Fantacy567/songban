import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.parent_report import request_parent_model
from app.planner import PlannerError
from scripts.run_demo import build_demo


def answer(context):
    return {'mode': 'fixture', 'requested_model': 'fixture', 'actual_model': 'fixture', 'analysis': {
        'summary': context['child_name'] + '正在根据自己的兴趣参与小队创作。',
        'observations': [{'title': '自己的目标', 'detail': '写下了想尝试的工作，可以继续核对具体分工。', 'source_ids': ['profile']},
                         {'title': '回看已有经历', 'detail': '从自己填写的经历出发，讨论下一步想尝试的事情。', 'source_ids': ['preferences']}],
        'suggestions': ['请孩子介绍自己想做的作品。', '一起选择一项想继续尝试的小任务。']}}


class ParentReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / 'demo.sqlite3'
        cls.calls = []
        cls.failure = None

        def runner(context):
            cls.calls.append(context)
            if cls.failure:
                raise cls.failure
            return answer(context)

        cls.app = build_demo(cls.path, parent_report_runner=runner)
        cls.client = TestClient(cls.app)
        cls.demo = json.loads(cls.client.get('/demo/bootstrap.js').text.split('=', 1)[1].split(';\n', 1)[0])
        cls.sid = cls.demo['team']['id']
        cls.headers = {'Authorization': 'Bearer ' + cls.demo['users'][0]['token']}
        cls.url = '/api/core/teams/' + cls.sid + '/parent-report'

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.tmp.cleanup()

    def setUp(self):
        type(self).calls.clear()
        type(self).failure = None

    def body(self, **changes):
        return {'request_id': uuid.uuid4().hex, 'draft': '我想练习把设计理由讲给队友听。', **changes}

    def test_only_child_records_sent_to_model(self):
        response = self.client.post(self.url, headers=self.headers, json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['model']['mode'], 'fixture')
        self.assertEqual(data['input']['person']['id'], 'demo-lin')
        self.assertEqual(len(data['input']['snapshot']['members']), 1)
        self.assertTrue(all(t['owner_id'] == 'demo-lin' for t in data['input']['snapshot']['active_plan']['tasks']))
        sent = json.dumps(self.calls[0], ensure_ascii=False)
        self.assertIn('把设计理由讲给队友听', sent)
        self.assertNotIn('demo-zhou', sent)
        self.assertNotIn('token', sent)
        self.assertNotIn('password', sent)
        self.assertIn('本人填写的', data['analysis']['observations'][0]['source'])

    def test_idempotent_retry_does_not_call_model_twice(self):
        body = self.body()
        first = self.client.post(self.url, headers=self.headers, json=body)
        again = self.client.post(self.url, headers=self.headers, json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), again.json())
        changed = self.client.post(self.url, headers=self.headers, json=body | {'draft': '改变了内容'})
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(len(self.calls), 1)

    def test_switching_member_uses_the_new_childs_own_tasks(self):
        headers = {'Authorization': 'Bearer ' + self.demo['users'][1]['token']}
        response = self.client.post(self.url, headers=headers, json=self.body(draft='我在练习页面开发。'))
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['input']['person']['id'], 'demo-zhou')
        self.assertTrue(all(t['owner_id'] == 'demo-zhou' for t in data['input']['snapshot']['active_plan']['tasks']))
        self.assertEqual(self.calls[0]['child_name'], self.demo['users'][1]['name'])
        self.assertNotIn('梳理使用场景', json.dumps(self.calls[0], ensure_ascii=False))

    def test_model_failure_is_explicit_and_never_replaced(self):
        type(self).failure = PlannerError('model_timeout', '模型超时，没有采用报告。', 504)
        body = self.body()
        first = self.client.post(self.url, headers=self.headers, json=body)
        again = self.client.post(self.url, headers=self.headers, json=body)
        self.assertEqual(first.status_code, 504)
        self.assertEqual(again.status_code, 504)
        self.assertNotIn('analysis', first.json())
        self.assertEqual(len(self.calls), 1)

    def test_unauthorized_other_members_and_connectors_cannot_generate_for_child(self):
        self.assertEqual(self.client.post(self.url, json=self.body()).status_code, 401)
        self.assertEqual(self.client.post(self.url, headers=self.headers, json=self.body(user_id='demo-zhou')).status_code, 422)
        connection = self.client.post('/api/core/teams/' + self.sid + '/connections', headers=self.headers, json={'label': 'report permission fixture'}).json()
        self.assertEqual(self.client.post(self.url, headers={'Authorization': 'Bearer ' + connection['token']}, json=self.body()).status_code, 403)
        guest = self.client.post('/api/core/guest-session').json()
        self.assertEqual(self.client.post(self.url, headers={'Authorization': 'Bearer ' + guest['token']}, json=self.body()).status_code, 403)
        self.assertFalse(self.calls)

    def test_saved_reflection_beats_unedited_demo_prefill(self):
        report = self.client.post('/api/core/teams/' + self.sid + '/reports', headers=self.headers,
                                 json={'event_id': uuid.uuid4().hex, 'summary': '复盘：这是孩子保存的最新收获。', 'tool': '网页复盘', 'origin': 'human', 'status': 'discussion'})
        self.assertEqual(report.status_code, 200, report.text)
        response = self.client.post(self.url, headers=self.headers, json=self.body(draft='预填的旧示例', draft_is_example=True))
        self.assertEqual(response.status_code, 200)
        reflection = next(s for s in self.calls[0]['sources'] if s['id'] == 'reflection')
        self.assertEqual(reflection['content'], '这是孩子保存的最新收获。')

    def test_bad_source_citations_are_rejected(self):
        with patch(__name__ + '.answer', return_value={'mode': 'fixture', 'analysis': {'summary': '内容', 'observations': [
                {'title': '观察', 'detail': '内容', 'source_ids': ['another-child']},
                {'title': '观察2', 'detail': '内容', 'source_ids': ['profile']}], 'suggestions': ['建议1', '建议2']}}):
            response = self.client.post(self.url, headers=self.headers, json=self.body())
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('analysis', response.json())

    def test_resume_preserves_people_teams_and_existing_records(self):
        with closing(sqlite3.connect(self.path)) as con:
            before = {t: con.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in ('people', 'squads', 'core_reports')}
        resumed = TestClient(build_demo(self.path, resume=self.demo, parent_report_runner=answer))
        try:
            data = resumed.get('/api/core/me', headers=self.headers)
            self.assertEqual(data.status_code, 200)
            self.assertEqual(data.json()['person']['id'], 'demo-lin')
            with closing(sqlite3.connect(self.path)) as con:
                after = {t: con.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in before}
            self.assertEqual(after, before)
        finally:
            resumed.close()


class ParentReportModelTests(unittest.TestCase):
    def test_missing_key_never_generates_template(self):
        with self.assertRaises(PlannerError) as error:
            request_parent_model({'sources': []}, {})
        self.assertEqual(error.exception.code, 'model_not_configured')

    def test_http_protocol_metadata_and_incomplete_reply(self):
        config = {'api_key': 'fixture-private-key', 'base_url': 'https://api.deepseek.com', 'model_id': 'requested-fixture'}
        real_client = httpx.Client
        seen = []
        finish = ['stop']

        def transport(request):
            body = json.loads(request.content)
            seen.append(body)
            return httpx.Response(200, json={'model': 'actual-fixture', 'choices': [{'finish_reason': finish[0],
                                  'message': {'content': json.dumps(answer({'child_name': '孩子'})['analysis'])}}]})

        with patch('app.parent_report.httpx.Client', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(transport))):
            result = request_parent_model({'child_name': '孩子', 'sources': []}, config)
            self.assertEqual(result['mode'], 'live')
            self.assertEqual(result['actual_model'], 'actual-fixture')
            self.assertEqual(seen[0]['thinking']['type'], 'disabled')
            self.assertNotIn('fixture-private-key', json.dumps(seen))
            finish[0] = 'length'
            with self.assertRaises(PlannerError) as error:
                request_parent_model({'sources': []}, config)
            self.assertEqual(error.exception.code, 'report_invalid_output')


if __name__ == '__main__':
    unittest.main()
