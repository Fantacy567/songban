"""Central registration and archive projection regressions, synthetic data only."""
from dataclasses import replace
from pathlib import Path
import unittest

from app.creative_studio.service import START
from app.server_admin import AdminSettings
from app.platform_v1.schemas import WorkList, WorkDetail
from tests.test_learning_v2_identity import Fixture, BASE, ORIGIN
from tests import test_platform_http as baseline


class CreativeIntegrationTests(Fixture, unittest.TestCase):
    post = baseline.PlatformHttpTests.post
    provider = baseline.PlatformHttpTests.provider

    def setUp(self):
        baseline.PlatformHttpTests.setUp(self)
        platform = replace(self.platform_settings, navigation_enabled=True, creative_studio_enabled=True)
        self.app = self.factory(self.path, core_only=True, learning_settings=self.settings,
                               platform_settings=platform,
                               server_admin_settings=AdminSettings(allowed_emails=('parent-a@example.test',),
                                   secret_dir=Path(self.tmp.name)/'admin-secrets'))
        self.service = self.app.state.learning_v2
        self.service.clock = lambda: self.now[0]
        self.a, self.b = self.client(), self.client()
        self.login(self.a, 'parent-a')
        self.enter(self.a, self.lid)

    def create(self, *args, **kwargs):
        # Baseline setUp uses Fixture.create to establish the synthetic family.
        return Fixture.create(self, *args, **kwargs)

    def project(self):
        return self.post('/studio/projects', {'title':'真实按钮示例', 'idea':'点击按钮改变一句话。'}, 201)

    def test_main_registers_opt_in_and_keeps_shell_csp(self):
        html = self.a.get('/')
        self.assertIn('name="songban-creative-studio"', html.text)
        self.assertIn("script-src 'self';", html.headers['content-security-policy'])
        self.assertNotIn("script-src 'self' 'unsafe-inline'", html.headers['content-security-policy'])
        self.assertIn("frame-ancestors 'none'", self.a.get('/server-admin').headers['content-security-policy'])

    def test_saved_preview_has_separate_csp_and_owner_check(self):
        p = self.project()
        url = self.a.get('/api/platform/v1/studio/projects/'+p['id']+'/preview').json()['document_url']
        response = self.a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('sandbox allow-scripts', response.headers['content-security-policy'])
        self.assertNotIn('allow-same-origin', response.headers['content-security-policy'])
        self.assertEqual(self.b.get(url).status_code, 401)

    def test_archive_is_visible_to_child_and_authorized_parent(self):
        p = self.project()
        p = self.post('/studio/projects/'+p['id']+'/archive', {'expected_revision':p['revision'],
                        'contribution':'我预测了点击后的文字，运行并核对了结果。'})
        url = '/api/platform/v1/learners/'+self.lid+'/works'
        result = self.a.get(url)
        self.assertEqual(result.status_code, 200, result.text)
        works = WorkList.model_validate(result.json())
        item = next(w for w in works.items if w.id == p['archive']['id'])
        self.assertEqual(item.available_actions, ['open_studio'])
        detail = self.a.get(url+'/'+item.id)
        self.assertEqual(detail.status_code, 200, detail.text)
        WorkDetail.model_validate(detail.json())
        self.login(self.b, 'parent-a')
        self.assertEqual(self.b.get(url+'/'+item.id).status_code, 200)

    def test_child_cannot_use_admin_parent_bearer_and_manager_can_configure(self):
        response = self.a.get('/api/server-admin/v1/session', headers={'Authorization':'Bearer old-parent-a'})
        self.assertEqual(response.status_code, 403)
        self.login(self.b, 'parent-a')
        response = self.b.get('/api/server-admin/v1/session')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['runtime']['creative_studio_registered'])
        self.assertNotIn('api_key', response.json()['providers']['text'])

    def test_default_runtime_no_paid_call_and_curriculum_draft(self):
        p = self.project()
        self.assertFalse(p['runtime']['available'])
        self.post('/studio/projects/'+p['id']+'/messages', {'expected_revision':p['revision'], 'text':'帮我修改颜色'}, 503)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
