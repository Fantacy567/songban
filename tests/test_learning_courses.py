# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Real in-process HTTP + SQLite tests, synthetic identity/content, no providers."""
import copy
import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app.learning_courses import register_courses
from app.learning_courses.catalog import COURSE_KINDS, Catalog
from app.learning_courses.service import NOTICE
from app.learning_courses.storage import MIGRATION
from app.platform_v1 import PlatformService, PlatformSettings
from pydantic import ValidationError

try:
    from .test_learning_v2_identity import Fixture, ORIGIN
except ImportError:
    from test_learning_v2_identity import Fixture, ORIGIN

PREFIX = '/api/platform/v1'
EXPERIMENT = PREFIX+'/learning-courses/api/experiment'
ACTIVITIES = {
    'ai-tools': {'sequence': ['describe', 'generate', 'run', 'check', 'improve']},
    'imagination': {'audience': '同学', 'problem': '忘记浇水', 'feature': '提醒', 'check': '观察提醒'},
    'first-project': {'change': '修改按钮文字', 'observation': '点击后变化'},
    'plugins': {'enabled': False, 'before': '普通画布', 'after': '打开标尺'},
    'models': {'choice': 'sample-a', 'reason': '示例更符合要求'},
    'api': {'name': '测试名字', 'message': '固定规则响应'},
    'model-powered-app': {'input': '一句话', 'role': '改写', 'output': '建议', 'fallback': '请自己修改'},
}


def catalog_fixture():
    """Never create/overwrite the C01-owned production catalog."""
    courses = []
    for order, (cid, kind) in enumerate(COURSE_KINDS.items(), 1):
        courses.append({
            'id': cid, 'version': '1', 'title': '测试课程 '+cid,
            'chapter': {'id': 'tools' if order <= 4 else 'advanced',
                        'title': 'AI 工具篇' if order <= 4 else '进阶篇', 'order': 1 if order <= 4 else 2},
            'order': order, 'status': 'trial', 'goal': '观察并解释', 'preparation': '阅读说明',
            'duration': '可分次尝试', 'cover': {'src': f'/static/platform/illustrations/course-{cid}.svg', 'alt': cid+' 测试插画'},
            'intro': '隔离测试内容，不是教学审核证据。',
            'steps': [{'id': step, 'title': step, 'instruction': '测试 '+cid, 'example': '示例', 'prompt': '记录'}
                      for step in ('understand', 'try', 'reflect')],
            'activity': {'kind': kind, 'title': '测试活动', 'instruction': '试一试'},
            'sources': [{'title': '合成测试资料', 'url': 'https://example.test/source', 'supports': '仅校验结构'}],
            'review': {'technical': 'draft', 'education': 'pending', 'pilot': 'pending'},
        })
    return {'version': '1', 'courses': courses}


class LearningCoursesTests(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.catalog_path = Path(self.tmp.name) / 'synthetic-catalog.json'
        self.catalog_data = catalog_fixture()
        self.write_catalog(self.catalog_data)
        catalog_patch = patch('app.learning_courses.catalog.CATALOG_PATH', self.catalog_path)
        catalog_patch.start(); self.addCleanup(catalog_patch.stop)
        self.platform = PlatformService(self.service, PlatformSettings(enabled=True))
        self.platform.migrate()
        self.courses = register_courses(self.app, self.platform)
        self.lid, _ = self.create(self.a)
        self.enter(self.a, self.lid)

    def write_catalog(self, value):
        self.catalog_path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def url(self, cid='ai-tools'):
        return PREFIX+'/learning-courses/'+cid+'/progress'

    def headers(self, client=None):
        return {'Origin': ORIGIN, 'X-CSRF-Token': self.bootstrap(client or self.a)['csrf_token']}

    def body(self, **values):
        return {'request_id': self.rid(), 'expected_revision': 0,
                'answers': {'understand': '', 'try': '', 'reflect': ''}, 'activity': {}, 'project_id': None, **values}

    def save(self, cid='ai-tools', body=None, status=200, client=None):
        client = client or self.a
        response = client.post(self.url(cid), json=body or self.body(), headers=self.headers(client))
        self.assertEqual(response.status_code, status, response.text)
        self.assertIn('no-store', response.headers['cache-control'])
        return response.json()

    def get_progress(self, cid='ai-tools', client=None, status=200):
        response = (client or self.a).get(self.url(cid))
        self.assertEqual(response.status_code, status, response.text)
        self.assertIn('no-store', response.headers['cache-control'])
        return response.json()

    def experiment(self, body=None, status=200, client=None):
        client = client or self.a
        body = body if body is not None else {'request_id': self.rid(), 'operation': 'greet', 'name': '小松'}
        response = client.post(EXPERIMENT, json=body, headers=self.headers(client))
        self.assertEqual(response.status_code, status, response.text)
        self.assertIn('no-store', response.headers['cache-control'])
        return response.json()

    def count(self, table):
        # All callers use hard-coded test table names.
        with self.service.store.transaction() as con:
            return con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def test_public_catalog_and_seven_details_need_no_identity(self):
        response = self.b.get(PREFIX+'/learning-catalog')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), self.catalog_data)
        self.assertNotIn('set-cookie', response.headers)
        self.assertIn('no-store', response.headers['cache-control'])
        for course in self.catalog_data['courses']:
            with self.subTest(course=course['id']):
                response = self.b.get(PREFIX+'/learning-catalog/'+course['id'])
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), course)
        self.assertEqual(self.count('learning_course_progress'), 0)

    def test_unknown_course_returns_404_without_writes(self):
        response = self.b.get(PREFIX+'/learning-catalog/not-a-course')
        self.assertEqual(response.status_code, 404)
        self.get_progress('not-a-course', status=404)
        self.save('not-a-course', status=404)
        self.assertEqual(self.count('learning_course_progress'), 0)
        self.assertEqual(self.count('platform_requests'), 0)

    def test_public_host_origin_transport_and_query_checks(self):
        for path in (PREFIX+'/learning-catalog', PREFIX+'/learning-catalog/api'):
            for headers in ({'Origin': 'https://foreign.test'}, {'Host': 'foreign.test'}, {'Sec-Fetch-Site': 'cross-site'}):
                with self.subTest(path=path, headers=headers):
                    self.assertEqual(self.b.get(path, headers=headers).status_code, 403)
            self.assertEqual(self.b.get('http://learning.example.test'+path).status_code, 403)
            self.assertEqual(self.b.get(path+'?learner_id=someone').status_code, 422)
            self.assertEqual(self.b.get(path, headers={'Origin': ORIGIN}).status_code, 200)

    def test_public_disabled_hides_catalog_but_private_history_survives(self):
        saved = self.save()
        self.platform.settings = replace(self.platform.settings, enabled=False)
        for path in (PREFIX+'/learning-catalog', PREFIX+'/learning-catalog/api'):
            response = self.b.get(path)
            self.assertEqual(response.status_code, 423)
            self.assertEqual(response.json()['error']['code'], 'platform_paused')
            self.assertNotIn('courses', response.json())
        self.assertEqual(self.get_progress(), saved)
        self.save(body=self.body(expected_revision=1), status=423)
        self.experiment(status=423)

    def test_learning_pause_blocks_new_writes_and_replays_preserves_history(self):
        body = self.body()
        saved = self.save(body=body)
        self.service.settings = replace(self.service.settings, enabled=False)
        self.assertEqual(self.b.get(PREFIX+'/learning-catalog').status_code, 423)
        self.assertEqual(self.get_progress(), saved)
        self.assertEqual(self.save(body=body, status=423)['error']['code'], 'learning_paused')
        self.experiment(status=423)

    def test_missing_or_bad_catalog_fails_closed_history_remains_readable(self):
        saved = self.save()
        for raw in ('{}', '{', '{"version":"1","version":"2"}', '\ufeff{"courses": []}'):
            self.catalog_path.write_text(raw, encoding='utf-8')
            self.assertEqual(self.b.get(PREFIX+'/learning-catalog').status_code, 503)
            self.assertEqual(self.get_progress(), saved)
            self.save(body=self.body(expected_revision=1), status=503)
        with patch('app.learning_courses.catalog.CATALOG_PATH', self.catalog_path.with_name('missing.json')):
            self.assertEqual(self.b.get(PREFIX+'/learning-catalog').status_code, 503)

    def test_catalog_validates_frozen_mapping_and_source_structure(self):
        changes = [lambda x: x['courses'].pop(), lambda x: x['courses'].__setitem__(1, x['courses'][0]),
                   lambda x: x['courses'][0].update(order=2), lambda x: x['courses'][0]['chapter'].update(id='advanced'),
                   lambda x: x['courses'][0]['activity'].update(kind='project'),
                   lambda x: x['courses'][0]['cover'].update(src='https://foreign.test/cover.svg'),
                   lambda x: x['courses'][0]['steps'][0].update(id='reflect'),
                   lambda x: x['courses'][0]['sources'][0].update(url='javascript:alert(1)'),
                   lambda x: x['courses'][0]['review'].update(education='approved')]
        for change in changes:
            value = copy.deepcopy(self.catalog_data); change(value)
            with self.subTest(change=changes.index(change)), self.assertRaises(ValidationError):
                Catalog.model_validate(value)

    def test_default_draft_and_partial_answers_are_saved_without_mastery(self):
        initial = self.get_progress()
        self.assertEqual(initial, {'course_id': 'ai-tools', 'course_version': '1', 'learner_id': self.lid,
            'revision': 0, 'answers': {'understand': '', 'try': '', 'reflect': ''}, 'activity': {},
            'project_id': None, 'updated_at': None, 'status': 'not_started'})
        body = self.body(answers={'understand': '先运行再检查', 'try': '', 'reflect': ''})
        saved = self.save(body=body)
        self.assertEqual(saved['answers'], body['answers'])
        self.assertEqual(saved['status'], 'saved')
        self.assertEqual(saved['revision'], 1)
        self.assertTrue(saved['updated_at'])
        self.assertEqual(set(saved), set(initial))
        self.assertEqual(self.get_progress(), saved)

    def test_all_seven_activities_are_independently_saved(self):
        for cid, activity in ACTIVITIES.items():
            with self.subTest(course=cid):
                saved = self.save(cid, self.body(activity=activity))
                self.assertEqual(saved['activity'], activity)
                self.assertEqual(saved['course_id'], cid)
                self.assertEqual(saved['revision'], 1)
                self.assertEqual(self.get_progress(cid), saved)
        self.assertEqual(self.count('learning_course_progress'), 7)
        self.assertEqual(self.get_progress('ai-tools')['activity'], ACTIVITIES['ai-tools'])

    def test_empty_activity_allowed_for_every_course(self):
        for cid in COURSE_KINDS:
            with self.subTest(course=cid):
                self.assertEqual(self.save(cid)['activity'], {})

    def test_activity_unknown_missing_wrong_types_and_oversized_fields(self):
        for cid, activity in ACTIVITIES.items():
            variants = [dict(activity, extra='forbidden')]
            missing = dict(activity); missing.pop(next(iter(missing))); variants.append(missing)
            for key, value in activity.items():
                variants.append(dict(activity, **{key: None}))
                if isinstance(value, str):
                    variants.append(dict(activity, **{key: 42}))
                    variants.append(dict(activity, **{key: 'x'*2001}))
            for invalid in variants:
                if not invalid:  # Empty is explicitly allowed.
                    continue
                with self.subTest(course=cid, invalid=invalid):
                    self.save(cid, self.body(activity=invalid), status=422)
        self.assertEqual(self.count('learning_course_progress'), 0)

    def test_activity_limits_and_enums(self):
        limits = {'imagination': {'audience': 500, 'problem': 500, 'feature': 500, 'check': 500},
                  'first-project': {'change': 1000, 'observation': 1000},
                  'plugins': {'before': 1000, 'after': 1000}, 'models': {'reason': 1000},
                  'api': {'name': 40, 'message': 200},
                  'model-powered-app': {'input': 500, 'role': 500, 'output': 500, 'fallback': 500}}
        for cid, fields in limits.items():
            activity = {**ACTIVITIES[cid], **{key: '中'*limit for key, limit in fields.items()}}
            self.save(cid, self.body(activity=activity))
            for key, limit in fields.items():
                self.save(cid, self.body(expected_revision=1, activity={**activity, key: '中'*(limit+1)}), status=422)
        for sequence in (['describe', 'describe'], ['execute'], ['describe']*6, 'describe', [1]):
            self.save(body=self.body(activity={'sequence': sequence}), status=422)
        self.save(body=self.body(activity={'sequence': []}))
        for value in ('true', 1, None):
            self.save('plugins', self.body(activity={**ACTIVITIES['plugins'], 'enabled': value}), status=422)
        for value in ('provider-a', '', None):
            self.save('models', self.body(activity={'choice': value, 'reason': ''}), status=422)
        for i, value in enumerate(('sample-b', 'undecided'), 1):
            self.save('models', self.body(expected_revision=i, activity={'choice': value, 'reason': ''}))

    def test_strict_answers_revision_and_outer_fields(self):
        valid = self.body()
        invalids = [dict(valid, learner_id=self.lid), dict(valid, course_id='models'), dict(valid, status='passed'),
                    dict(valid, expected_revision=-1), dict(valid, expected_revision=True), dict(valid, expected_revision='0'),
                    dict(valid, request_id='bad id'), dict(valid, activity=[]), dict(valid, project_id=123),
                    dict(valid, answers={'understand': ''}), dict(valid, answers=[])]
        for field in ('understand', 'try', 'reflect'):
            for value in ('x'*2001, None, 4):
                invalids.append(dict(valid, answers={**valid['answers'], field: value}))
        invalids.append(dict(valid, answers={**valid['answers'], 'learner_id': self.lid}))
        for key in valid:
            item = dict(valid); item.pop(key); invalids.append(item)
        for body in invalids:
            with self.subTest(body=body):
                self.save(body=body, status=422)
        self.save(body=self.body(answers={key: '文'*2000 for key in valid['answers']}))

    def test_no_caller_selected_learner_in_queries_or_experiment(self):
        self.assertEqual(self.a.get(self.url()+'?learner_id=other').status_code, 422)
        self.assertEqual(self.a.post(self.url()+'?learner_id=other', json=self.body(), headers=self.headers()).status_code, 422)
        self.experiment({'request_id': self.rid(), 'operation': 'greet', 'name': '小松', 'learner_id': self.lid}, status=422)
        self.assertEqual(self.count('platform_requests'), 0)

    def test_learners_are_isolated_even_with_same_request_id(self):
        first_body = self.body(request_id='shared-request-id', answers={'understand': '甲的记录', 'try': '', 'reflect': ''})
        first = self.save(body=first_body)
        second_lid, _ = self.create(self.b, 'parent-b'); self.enter(self.b, second_lid)
        self.assertEqual(self.get_progress(client=self.b)['revision'], 0)
        other_body = {**first_body, 'answers': {'understand': '乙的记录', 'try': '', 'reflect': ''}}
        second = self.save(body=other_body, client=self.b)
        self.assertEqual(second['learner_id'], second_lid)
        self.assertEqual(self.get_progress(), first)
        self.assertEqual(self.get_progress(client=self.b), second)
        self.assertEqual(self.count('learning_course_progress'), 2)

    def test_only_current_learner_not_anonymous_parent_staff_or_bearer(self):
        self.get_progress(client=self.b, status=401)
        self.save(client=self.b, status=401)
        self.experiment(client=self.b, status=401)
        for actor in ('parent-a', 'reviewer'):
            self.login(self.b, actor)
            self.get_progress(client=self.b, status=403)
            self.save(client=self.b, status=403)
            self.experiment(client=self.b, status=403)
        bare = self.client()
        self.assertEqual(bare.get(self.url(), headers={'Authorization': 'Bearer old-outsider'}).status_code, 403)
        response = self.a.get(self.url(), headers={'Authorization': 'Bearer old-outsider'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['learner_id'], self.lid)

    def test_cookie_without_current_session_cannot_fall_back_to_bearer(self):
        stale = self.client(); stale.cookies.update(self.a.cookies)
        for cookie in list(stale.cookies.jar):
            if cookie.name == self.service.cookie_name:
                stale.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)
        self.assertEqual(stale.get(self.url(), headers={'Authorization': 'Bearer old-outsider'}).status_code, 403)

    def test_same_request_replay_is_exact_even_after_new_revision(self):
        body = self.body(activity=ACTIVITIES['ai-tools'])
        saved = self.save(body=body)
        later = self.save(body=self.body(expected_revision=1, answers={'understand': '新答案', 'try': '', 'reflect': ''}))
        self.assertEqual(self.save(body=body), saved)
        self.assertEqual(self.get_progress(), later)
        changed = self.save(body={**body, 'activity': {}}, status=409)
        self.assertEqual(changed['error']['code'], 'idempotency_conflict')
        self.assertEqual(self.count('platform_requests'), 2)

    def test_revision_conflict_preserves_last_saved_input(self):
        saved = self.save()
        result = self.save(body=self.body(), status=409)
        self.assertEqual(result['error']['code'], 'revision_conflict')
        self.assertEqual(result['error']['current_revision'], 1)
        self.assertEqual(self.get_progress(), saved)
        self.assertEqual(self.count('platform_requests'), 1)

    def parallel_posts(self, path, bodies):
        clients = [self.client() for _ in bodies]
        for client in clients:
            client.cookies.update(self.a.cookies)
        headers = self.headers()
        barrier = threading.Barrier(len(bodies))
        def execute(pair):
            client, body = pair
            barrier.wait(timeout=10)
            return client.post(path, json=body, headers=headers)
        with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
            return list(pool.map(execute, zip(clients, bodies)))

    def test_concurrent_identical_requests_commit_once(self):
        body = self.body(activity=ACTIVITIES['ai-tools'])
        responses = self.parallel_posts(self.url(), [body, body])
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(self.count('platform_requests'), 1)
        self.assertEqual(self.get_progress()['revision'], 1)

    def test_concurrent_different_requests_respect_expected_revision(self):
        responses = self.parallel_posts(self.url(), [self.body(), self.body()])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        conflict = next(r for r in responses if r.status_code == 409)
        self.assertEqual(conflict.json()['error']['code'], 'revision_conflict')
        self.assertEqual(self.count('platform_requests'), 1)
        self.assertEqual(self.get_progress()['revision'], 1)

    def test_concurrent_same_id_different_content_is_conflict(self):
        body = self.body()
        other = {**body, 'answers': {'understand': '不同内容', 'try': '', 'reflect': ''}}
        responses = self.parallel_posts(self.url(), [body, other])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        conflict = next(r for r in responses if r.status_code == 409)
        self.assertEqual(conflict.json()['error']['code'], 'idempotency_conflict')
        self.assertEqual(self.count('platform_requests'), 1)

    def test_csrf_origin_content_type_and_cross_site_rejected(self):
        for path, body in ((self.url(), self.body()), (EXPERIMENT, {'request_id': self.rid(), 'operation': 'greet', 'name': '测试'})):
            for headers in ({}, {'Origin': ORIGIN}, {**self.headers(), 'X-CSRF-Token': 'bad'},
                            {**self.headers(), 'Origin': 'https://foreign.test'}, {**self.headers(), 'Sec-Fetch-Site': 'cross-site'}):
                with self.subTest(path=path, headers=headers):
                    self.assertEqual(self.a.post(path, json=body, headers=headers).status_code, 403)
            self.assertEqual(self.a.post(path, content=json.dumps(body), headers={**self.headers(), 'Content-Type': 'text/plain'}).status_code, 415)
        self.assertEqual(self.count('platform_requests'), 0)

    def test_malformed_duplicate_json_and_body_size_are_bounded(self):
        for path in (self.url(), EXPERIMENT):
            for payload in ('{', '{"request_id":"a","request_id":"b"}', '{"name":NaN}', '{"name":"\\ud800"}'):
                response = self.a.post(path, content=payload, headers={**self.headers(), 'Content-Type': 'application/json'})
                self.assertEqual(response.status_code, 422, response.text)
            response = self.a.post(path, content=' '*65537, headers={**self.headers(), 'Content-Type': 'application/json'})
            self.assertEqual(response.status_code, 413)
        self.assertEqual(self.count('platform_requests'), 0)

    def test_mode_epoch_change_rejects_old_session_and_old_csrf(self):
        body = self.body(); self.save(body=body)
        stale = self.client(); stale.cookies.update(self.a.cookies)
        old_headers = self.headers()
        self.login(self.a, 'parent-a')
        self.assertEqual(stale.get(self.url(), headers={'Authorization': 'Bearer old-outsider'}).status_code, 401)
        self.assertEqual(stale.post(self.url(), json=body, headers=old_headers).status_code, 401)
        self.enter(self.a, self.lid)
        self.assertEqual(self.a.post(self.url(), json=self.body(expected_revision=1), headers=old_headers).status_code, 403)
        self.assertEqual(self.get_progress()['revision'], 1)

    def test_session_expiry_blocks_progress_and_experiment(self):
        headers = self.headers(); self.now[0] += self.settings.session_seconds+1
        self.get_progress(status=401)
        response = self.a.post(EXPERIMENT, json={'request_id': self.rid(), 'operation': 'greet', 'name': '测试'}, headers=headers)
        self.assertEqual(response.status_code, 401)

    def test_learning_consent_revocation_blocks_history_and_replay(self):
        body = self.body(); self.save(body=body)
        exp = {'request_id': self.rid(), 'operation': 'greet', 'name': '测试'}; self.experiment(exp)
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_consents SET scopes='[\"parent_summary\"]' WHERE learner_id=?", (self.lid,))
        self.get_progress(status=403)
        self.save(body=body, status=403)
        self.experiment(exp, status=403)
        self.assertEqual(self.count('platform_requests'), 2)

    def test_relationship_revocation_blocks_read_and_write(self):
        self.save()
        with self.service.store.transaction() as con:
            con.execute("UPDATE learn_links SET status='revoked' WHERE learner_id=?", (self.lid,))
        self.get_progress(status=403)
        self.save(status=403)
        self.experiment(status=403)

    def test_final_identity_recheck_rolls_back_progress_and_receipt(self):
        original = self.courses.write
        def revoked(con, op, session, params, body):
            result = original(con, op, session, params, body)
            con.execute('UPDATE learn_sessions SET revoked=1 WHERE id=?', (session['id'],))
            return result
        with patch.object(self.courses, 'write', side_effect=revoked):
            self.save(status=401)
            self.experiment(status=401)
        self.assertEqual(self.count('learning_course_progress'), 0)
        self.assertEqual(self.count('platform_requests'), 0)

    def test_final_identity_recheck_protects_private_read(self):
        saved = self.save()
        original = self.courses.read
        def revoked(con, op, session, params, query):
            result = original(con, op, session, params, query)
            con.execute("UPDATE learn_consents SET scopes='[]' WHERE learner_id=?", (self.lid,))
            return result
        with patch.object(self.courses, 'read', side_effect=revoked):
            response = self.a.get(self.url())
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('answers', response.json())
        self.assertEqual(self.get_progress(), saved)

    def test_project_binding_requires_first_project_and_both_owner_fields(self):
        from app.creative_studio.service import StudioService
        StudioService(self.platform).migrate()
        other_lid, _ = self.create(self.b, 'parent-b')
        with self.service.store.transaction() as con:
            for pid, owner, lid in (('owned', 'learner:'+self.lid, self.lid), ('foreign', 'learner:'+other_lid, other_lid),
                                    ('bad-owner', 'participant:parent-a', self.lid), ('bad-lid', 'learner:'+self.lid, other_lid)):
                con.execute('INSERT INTO creative_projects VALUES(?,?,?,?,?,?,0,NULL,?,?)',
                            (pid, owner, 'parent-a', lid, '合成项目', '验证归属', self.service.stamp(), self.service.stamp()))
        for pid in ('missing', 'foreign', 'bad-owner', 'bad-lid'):
            self.save('first-project', self.body(project_id=pid), status=404)
        for cid in COURSE_KINDS:
            if cid != 'first-project':
                self.save(cid, self.body(project_id='owned'), status=422)
        saved = self.save('first-project', self.body(project_id='owned'))
        self.assertEqual(saved['project_id'], 'owned')
        self.assertIsNone(self.save('first-project', self.body(expected_revision=1))['project_id'])

    def test_project_binding_with_studio_not_installed_is_404(self):
        self.save('first-project', self.body(project_id='missing'), status=404)
        self.assertEqual(self.save('first-project')['revision'], 1)

    def test_project_binding_revalidated_before_replay(self):
        from app.creative_studio.service import StudioService
        StudioService(self.platform).migrate()
        with self.service.store.transaction() as con:
            con.execute('INSERT INTO creative_projects VALUES(?,?,?,?,?,?,0,NULL,?,?)',
                        ('owned', 'learner:'+self.lid, 'parent-a', self.lid, '合成项目', '验证归属', self.service.stamp(), self.service.stamp()))
        body = self.body(project_id='owned'); self.save('first-project', body)
        with self.service.store.transaction() as con:
            con.execute("UPDATE creative_projects SET owner='participant:other' WHERE id='owned'")
        self.save('first-project', body, status=404)

    def test_experiment_runs_real_local_rule_and_does_not_save_raw_input(self):
        body = {'request_id': self.rid(), 'operation': 'greet', 'name': '  独有隐私测试甲  '}
        result = self.experiment(body)
        self.assertEqual(result, {'kind': 'teaching-api', 'request': {'operation': 'greet', 'name': '独有隐私测试甲'},
                                 'response': {'message': '你好，独有隐私测试甲！'}, 'notice': NOTICE})
        self.assertEqual(self.experiment(body), result)
        self.assertEqual(self.count('platform_requests'), 1)
        self.assertEqual(self.count('learning_course_progress'), 0)
        with self.service.store.transaction() as con:
            dump = '\n'.join(con.iterdump())
        self.assertNotIn('独有隐私测试甲', dump)
        self.assertNotIn('你好，', dump)

    def test_experiment_invalid_fields_return_422_without_echo_or_receipts(self):
        base = {'request_id': self.rid(), 'operation': 'greet', 'name': '有效'}
        invalid = [dict(base, operation='generate'), dict(base, operation=None), dict(base, extra='secret'),
                   dict(base, name=''), dict(base, name='  \t\n'), dict(base, name='x'*41),
                   dict(base, name=5), dict(base, name=None), dict(base, name={'secret': 'private'})]
        for key in base:
            body = dict(base); body.pop(key); invalid.append(body)
        for body in invalid:
            with self.subTest(body=body):
                result = self.experiment(body, status=422)
                self.assertNotIn('private', json.dumps(result))
        self.assertEqual(self.count('platform_requests'), 0)
        self.assertEqual(self.experiment({**base, 'name': ' 中'*20})['request']['name'], (' 中'*20).strip())

    def test_experiment_idempotency_conflict_and_concurrency_do_not_repeat_rule(self):
        body = {'request_id': self.rid(), 'operation': 'greet', 'name': '测试'}
        with patch.object(self.courses, 'write', wraps=self.courses.write) as write:
            responses = self.parallel_posts(EXPERIMENT, [body, body])
            self.assertEqual([r.status_code for r in responses], [200, 200])
            self.assertEqual(responses[0].json(), responses[1].json())
            self.assertEqual(write.call_count, 1)
            self.experiment({**body, 'name': '其他'}, status=409)
            self.assertEqual(write.call_count, 1)

    def test_experiment_replay_does_final_identity_check(self):
        body = {'request_id': self.rid(), 'operation': 'greet', 'name': '测试'}
        self.experiment(body)
        original = self.platform.identity
        def identity(con, request, writing):
            session, recheck = original(con, request, writing)
            def final():
                con.execute('UPDATE learn_sessions SET revoked=1 WHERE id=?', (session['id'],))
                return recheck()
            return session, final
        with patch.object(self.platform, 'identity', side_effect=identity):
            self.experiment(body, status=401)
        self.assertEqual(self.count('platform_requests'), 1)

    def test_migration_is_additive_idempotent_and_checksum_protected(self):
        saved = self.save()
        with self.service.store.transaction() as con:
            before = list(con.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'learn_*' ORDER BY name"))
            old_checksums = list(con.execute('SELECT * FROM learn_migrations ORDER BY version'))
        self.courses.migrate(); self.service.migrate(); self.platform.migrate()
        self.assertEqual(self.get_progress(), saved)
        with self.service.store.transaction() as con:
            self.assertEqual([tuple(r) for r in before], [tuple(r) for r in con.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'learn_*' ORDER BY name")])
            self.assertEqual([tuple(r) for r in old_checksums], [tuple(r) for r in con.execute('SELECT * FROM learn_migrations ORDER BY version')])
            self.assertEqual(con.execute('SELECT COUNT(*) FROM platform_migrations WHERE version=?', (MIGRATION,)).fetchone()[0], 1)
            con.execute('UPDATE platform_migrations SET checksum=? WHERE version=?', ('tampered', MIGRATION))
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.courses.migrate()

    def test_registration_guard_and_restart_restore(self):
        body = self.body(); saved = self.save(body=body)
        with self.assertRaisesRegex(ValueError, 'already installed'):
            register_courses(self.app, self.platform)
        learning = self.new_service(); api = self.new_app(learning)
        platform = PlatformService(learning, self.platform.settings); platform.migrate()
        register_courses(api, platform)
        client = self.client(api); client.cookies.update(self.a.cookies)
        self.assertEqual(self.get_progress(client=client), saved)
        self.assertEqual(self.save(body=body, client=client), saved)

    def test_storage_unavailability_returns_safe_503(self):
        with patch.object(self.platform, 'perform', side_effect=sqlite3.OperationalError('internal secret path')):
            result = self.save(status=503)
            experiment = self.experiment(status=503)
        self.assertNotIn('internal secret path', json.dumps([result, experiment]))


if __name__ == '__main__':
    unittest.main()
