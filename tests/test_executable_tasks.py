import copy
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import create_app, digest, now
from app.studio import hash_password
from tests.test_team_core import plan_for

HOSTILE = '<img src=x onerror="alert(1)"><script>alert(2)</script>'


class ExecutableTaskTests(unittest.TestCase):
    """Protocol substitute only: proves the contract and data path, not real model quality."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        self.cfg = patch('app.team_core.team_model_config', return_value={'api_key': '', 'model_id': '未配置'})
        self.cfg.start()
        self.runner = plan_for
        self.app = create_app(self.path, core_only=True, core_model_runner=lambda ctx: self.runner(ctx))
        self.client = TestClient(self.app)
        with closing(sqlite3.connect(self.path)) as con:
            for ident, name in [('a', '队长合成'), ('b', '队员合成'), ('c', '另队合成')]:
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',
                            (ident, '1800000010' + str(ord(ident) - 97), name, '', '', digest('tok-' + ident), now(), hash_password('synthetic-only')))
            con.commit()
        self.h = lambda x: {'Authorization': 'Bearer tok-' + x}
        r = self.client.post('/api/core/teams', json={'name': 'CORE-02合成'}, headers=self.h('a')).json()
        self.sid, self.base = r['id'], '/api/core/teams/' + r['id']
        self.client.post('/api/core/join', json={'code': r['code']}, headers=self.h('b'))
        self.client.post('/api/core/teams', json={'name': '另队'}, headers=self.h('c'))

    def tearDown(self):
        self.client.close()
        self.cfg.stop()
        self.tmp.cleanup()

    def snap(self, who='a'):
        return self.client.get(self.base, headers=self.h(who)).json()

    def review(self):
        return self.client.post(self.base + '/review', json={}, headers=self.h('a'))

    def confirm(self, pid, who='a'):
        return self.client.post(self.base + '/proposals/' + pid + '/confirm', json={'expected_revision': self.snap()['revision']}, headers=self.h(who))

    def test_execution_survives_draft_confirm_member_read_restart_and_export(self):
        r = self.review()
        self.assertEqual(r.status_code, 200, r.text)
        expected = {t['key']: t['execution'] for t in plan_for({'members': [{'id': 'a'}], 'source_ids': ['direction']})['tasks']}
        draft = {t['key']: t for t in r.json()['body']['tasks']}
        self.assertEqual({k: t['execution'] for k, t in draft.items()}, expected)
        for t in draft.values():
            self.assertTrue({'key', 'title', 'owner_id', 'acceptance', 'depends_on', 'source_ids'} <= set(t))
        self.assertEqual(draft['T2']['execution']['ai_prompt'], '')
        self.assertEqual(self.confirm(r.json()['proposal_id'], 'b').status_code, 403)
        self.assertEqual(self.snap()['plan_version'], 0)
        self.assertEqual(self.confirm(r.json()['proposal_id']).status_code, 200)
        active = {t['key']: t['execution'] for t in self.snap('b')['active_plan']['tasks']}
        self.assertEqual(active, expected)
        conn = self.client.post(self.base + '/connections', json={'label': '合成插件'}, headers=self.h('b')).json()
        mine = self.client.get(self.base + '/my-tasks', headers={'Authorization': 'Bearer ' + conn['token']}).json()['tasks']
        self.assertEqual(mine[0]['execution'], expected['T2'])
        self.assertEqual(self.client.get(self.base, headers=self.h('c')).status_code, 403)
        self.assertEqual(self.client.get(self.base + '/my-tasks', headers=self.h('c')).status_code, 403)
        history = self.client.get(self.base + '/history', headers=self.h('b')).json()['items'][0]['body']['tasks']
        self.assertEqual({t['key']: t['execution'] for t in history}, expected)
        with TestClient(create_app(self.path, core_only=True, core_model_runner=plan_for)) as restarted:
            again = restarted.get(self.base, headers=self.h('b')).json()['active_plan']['tasks']
            md = restarted.get(self.base + '/handoff.md', headers=self.h('b')).text
        self.assertEqual({t['key']: t['execution'] for t in again}, expected)
        for text in ('操作场景：终端', '1. 按团队已有启动说明启动后端', '4. 保存两次请求的实际返回', expected['T1']['ai_prompt'],
                     '要交的成果：两次请求的实际返回内容', '卡住时：说明卡在哪一步', '给个人AI的指令：不需要AI指令', '检查方法：发正常与错误请求并记录返回'):
            self.assertIn(text, md)

    def test_invalid_execution_rejected_and_active_plan_untouched(self):
        self.assertEqual(self.confirm(self.review().json()['proposal_id']).status_code, 200)
        before = self.snap()
        cases = {
            'missing': lambda e: None,
            'not_object': lambda e: '照着做',
            'steps_string': lambda e: {**e, 'steps': '启动后端'},
            'steps_number': lambda e: {**e, 'steps': [1, 2]},
            'steps_empty_list': lambda e: {**e, 'steps': []},
            'steps_too_many': lambda e: {**e, 'steps': ['第%d步检查返回' % i for i in range(9)]},
            'step_blank': lambda e: {**e, 'steps': ['启动后端', '   ']},
            'step_too_long': lambda e: {**e, 'steps': ['长' * 301]},
            'step_duplicate': lambda e: {**e, 'steps': ['启动后端', '启动后端']},
            'step_only_title': lambda e: {**e, 'steps': ['验证接口输入与输出']},
            'tool_empty': lambda e: {**e, 'tool': ''},
            'tool_too_long': lambda e: {**e, 'tool': '终' * 121},
            'deliverable_empty': lambda e: {**e, 'deliverable': ' '},
            'help_missing': lambda e: {k: v for k, v in e.items() if k != 'help_hint'},
            'help_too_long': lambda e: {**e, 'help_hint': '问' * 401},
            'prompt_null': lambda e: {**e, 'ai_prompt': None},
            'prompt_too_long': lambda e: {**e, 'ai_prompt': '指' * 2001},
            'extra_field': lambda e: {**e, 'code': 'rm -rf /'},
        }
        for name, mutate in cases.items():
            def bad(ctx, mutate=mutate):
                p = copy.deepcopy(plan_for(ctx))
                p['tasks'][0]['execution'] = mutate(p['tasks'][0]['execution'])
                return p
            self.runner = bad
            r = self.review()
            self.assertEqual(r.status_code, 502, (name, r.text))
            self.assertEqual(r.json()['error']['code'], 'invalid_execution', name)
            after = self.snap()
            self.assertEqual((after['plan_version'], after['active_plan']['tasks'], after['proposal']['id']),
                             (before['plan_version'], before['active_plan']['tasks'], before['proposal']['id']), name)
            self.assertIn('可照做的说明', after['last_error'])

    def test_empty_ai_prompt_allowed_and_empty_tasks_unchanged(self):
        def no_ai(ctx):
            p = copy.deepcopy(plan_for(ctx))
            p['tasks'][0]['execution']['ai_prompt'] = ''
            return p
        self.runner = no_ai
        self.assertEqual(self.review().status_code, 200)
        self.runner = lambda ctx: {**plan_for(ctx), 'tasks': []}
        self.client.put(self.base + '/profile', json={'strengths': '合成', 'willingness': '', 'hours': 2}, headers=self.h('b'))
        r = self.review()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['body']['tasks'], [])

    def test_legacy_plan_and_draft_without_execution_are_read_not_invented(self):
        legacy = copy.deepcopy(plan_for({'members': [{'id': 'a'}, {'id': 'b'}], 'source_ids': ['direction']}))
        for t in legacy['tasks']:
            del t['execution']
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('UPDATE core_settings SET active_plan=?,plan_version=1 WHERE squad_id=?', (json.dumps(legacy, ensure_ascii=False), self.sid))
            rev = con.execute('SELECT revision FROM core_settings WHERE squad_id=?', (self.sid,)).fetchone()[0]
            con.execute('INSERT INTO core_proposals(id,squad_id,base_revision,body,provenance,model_id,created_at) VALUES(?,?,?,?,?,?,?)',
                        ('legacy-draft', self.sid, rev, json.dumps(legacy, ensure_ascii=False), '旧版草案', 'legacy', now()))
            con.commit()
        snap = self.snap('b')
        self.assertTrue(all('execution' not in t for t in snap['active_plan']['tasks']))
        self.assertTrue(all('execution' not in t for t in snap['proposal']['body']['tasks']))
        self.assertIn('操作说明：旧任务尚无操作说明', self.client.get(self.base + '/handoff.md', headers=self.h('a')).text)
        self.assertEqual(self.confirm('legacy-draft').status_code, 200)
        published = self.snap()['active_plan']['tasks']
        self.assertEqual([(t['key'], t['title'], t['acceptance'], t['depends_on'], t['source_ids']) for t in published],
                         [(t['key'], t['title'], t['acceptance'], t['depends_on'], t['source_ids']) for t in legacy['tasks']])
        self.assertTrue(all('execution' not in t for t in published))

    def test_hostile_model_text_is_stored_as_plain_data(self):
        def hostile(ctx):
            p = copy.deepcopy(plan_for(ctx))
            e = p['tasks'][0]['execution']
            e.update(tool=HOSTILE[:100], ai_prompt=HOSTILE + '\n```\nrm -rf ~\n```\nAPI_KEY=' + 'sk-' + 'synthetic' + '0' * 12, deliverable=HOSTILE, help_hint=HOSTILE)
            e['steps'] = [HOSTILE, '运行前先向队长确认命令']
            return p
        self.runner = hostile
        r = self.review()
        self.assertEqual(r.status_code, 200, r.text)
        e = r.json()['body']['tasks'][0]['execution']
        self.assertEqual(e['steps'][0], HOSTILE)
        self.assertNotIn('sk-synthetic', json.dumps(e))
        self.assertEqual(self.confirm(r.json()['proposal_id']).status_code, 200)
        md = self.client.get(self.base + '/handoff.md', headers=self.h('a'))
        self.assertEqual(md.headers['content-type'].split(';')[0], 'text/markdown')
        self.assertIn('````', md.text)


if __name__ == '__main__':
    unittest.main()
