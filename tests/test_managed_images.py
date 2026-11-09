"""Managed Doubao integration with synthetic identity and MockTransport; no billing."""
from dataclasses import replace
from dataclasses import FrozenInstanceError
import json
import unittest
from unittest.mock import patch
import httpx

from app.learning_v2.protocol import Problem
from app.platform_v1 import PlatformService, register_platform
from app.server_admin import AdminSettings, register_server_admin
from tests.test_platform_images import ImageFixture


class ManagedImageTests(ImageFixture, unittest.TestCase):
    def respond(self, request):
        self.calls.append(json.loads(request.content))
        with self.service.store.transaction() as con:
            self.assertGreater(con.execute("SELECT COUNT(*) FROM platform_image_jobs WHERE state='dispatching'").fetchone()[0], 0)
        return self.hook(request) if self.hook else httpx.Response(200, json=self.response(), headers={'x-request-id':'synthetic-receipt'})

    def setUp(self):
        super().setUp()
        self.admin = register_server_admin(self.app, self.service,
            AdminSettings(allowed_emails=('parent-a@example.test',), secret_dir=self.path.parent/'private-keys'))
        platform = PlatformService(self.service, self.platform_settings)
        register_platform(self.app, platform)
        self.images = platform.images
        self.admin.bind_image_runtime(self.images, self.cfg)
        self.config_revision = 0
        self.configure()
        self.grant()

    def configure(self, **changes):
        # Management mutation under existing authorization fixture; tests below
        # additionally verify actual registered HTTP permission/CSRF boundaries.
        body = dict(request_id=self.rid(), expected_revision=self.config_revision, enabled=True,
                    model='synthetic-seedream', max_calls=6, max_output_tokens=800, timeout_seconds=60,
                    max_concurrency=1, api_key='synthetic-managed-key', clear_key=False,
                    size='2K', supports_sequential_generation=True, allowed_response_models=[])
        body.update(changes)
        with self.service.store.transaction() as con:
            result = self.admin.save(con, 'parent-a', 'image', body)
        self.config_revision = result['revision']
        return result

    def grant(self, count=6):
        self.images.grant_budget('learner:'+self.lid, count, grant_key=self.rid(),
                                 expires=self.now[0]+86400, authority='synthetic-review')

    def test_saved_admin_configuration_generates_with_frozen_adapter_and_private_archive(self):
        self.assertTrue(self.images.live_available)
        job = self.queue()
        result = self.images.execute(job['id'])
        self.assertEqual(result['state'], 'archived')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.content(result['asset_id'])[0], self.png)
        with self.service.store.transaction() as con:
            snapshot = con.execute('SELECT body FROM platform_image_input_snapshots WHERE job_id=?',(job['id'],)).fetchone()[0]
            self.assertIn('server-admin:image:1', snapshot)
            self.assertNotIn('synthetic-managed-key', snapshot)

    def test_config_rotation_cancels_queued_without_dispatch_and_needs_new_explicit_grant(self):
        job = self.queue()
        self.configure(api_key='synthetic-rotated-key')
        self.assertEqual(self.call('imageJob', job_id=job['id'])['state'], 'cancelled')
        result = self.images.execute(job['id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['usage']['status'], 'released')
        with self.assertRaises(Problem) as error: self.queue()
        self.assertEqual(error.exception.code, 'image_budget_required')
        self.assertEqual(self.calls, [])

    def test_runtime_interface_is_frozen_preserves_deployment_policy_and_original_service(self):
        original_config = self.images.config
        with self.service.store.transaction() as con:
            config = self.admin.image_runtime(self.cfg, con=con)
        with self.assertRaises(FrozenInstanceError):
            config.model = 'changed'
        self.assertEqual(config.storage_dir, self.cfg.storage_dir)
        self.assertEqual(config.image_consent_versions, self.cfg.image_consent_versions)
        self.images.execute(self.queue()['id'])
        self.assertIs(self.images, self.app.state.platform_v1.images)
        self.assertIs(self.images.config, original_config)

    def test_stale_operation_snapshot_cannot_dispatch_a_new_configuration_job(self):
        stale = self.admin.image_runtime()
        self.configure(api_key='synthetic-new-key')
        self.grant()
        job = self.queue()
        original = self.images.runtime_provider
        def provider(*, con=None):
            return stale if con is None else original(con=con)
        with patch.object(self.images, 'runtime_provider', provider):
            result = self.images.execute(job['id'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.calls, [])

    def test_enqueue_rechecks_configuration_in_current_transaction(self):
        original = self.images.runtime_provider
        stale = self.admin.image_runtime()
        self.configure(enabled=False, api_key='')
        calls = []
        def provider(*, con=None):
            calls.append(True)
            return stale if len(calls) == 1 else original(con=con)
        with patch.object(self.images, 'runtime_provider', provider):
            with self.assertRaises(Problem) as error:
                self.queue()
        self.assertEqual(error.exception.code, 'image_configuration_changed')
        self.assertEqual(self.calls, [])

    def test_unknown_survives_rotation_without_dispatch_or_refund(self):
        def timeout(request):
            raise httpx.ReadTimeout('synthetic', request=request)
        self.hook = timeout
        result = self.images.execute(self.queue()['id'])
        self.configure(enabled=False, clear_key=True, api_key='')
        for _ in range(3):
            result = self.images.execute(result['id'])
            self.images.worker_once()
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['usage']['status'], 'held')
        self.assertEqual(len(self.calls), 1)

    def test_revocation_during_provider_keeps_asset_private_without_binding(self):
        def during(_):
            self.configure(enabled=False, api_key='', clear_key=True)
            import httpx
            return httpx.Response(200, json=self.response())
        self.hook = during
        result = self.images.execute(self.queue()['id'])
        self.assertEqual(result['state'], 'archive_conflict')
        self.assertEqual(result['error_code'], 'image_configuration_changed')
        self.assertEqual(result['usage']['status'], 'settled')
        self.assertIsNone(self.bindings()['cover_asset_id'])
        self.assertEqual(self.content(result['asset_id'])[0], self.png)
        self.assertFalse(self.images.live_available)

    def test_revision_change_does_not_reset_cumulative_allowance(self):
        self.images.execute(self.queue()['id'])
        self.configure(max_calls=1)
        self.grant(1)
        self.work = self.external()
        with self.assertRaises(Problem) as error: self.queue()
        self.assertEqual(error.exception.code,'image_budget_required')
        self.assertEqual(len(self.calls),1)

    def test_inflight_concurrency_is_reserved_atomically(self):
        first = self.queue()
        self.work = self.external()
        second = self.queue()
        def during(_):
            result = self.images.execute(second['id'])
            self.assertEqual(result['state'],'queued')
            import httpx
            return httpx.Response(200, json=self.response())
        self.hook = during
        self.assertEqual(self.images.execute(first['id'])['state'],'archived')
        self.assertEqual(len(self.calls),1)
        self.hook = None
        self.assertEqual(self.images.execute(second['id'])['state'],'archived')

    def test_runtime_configuration_does_not_supply_image_consent(self):
        self.admin.image_base = replace(self.cfg,image_consent_versions=())
        self.grant()
        with self.assertRaises(Problem) as error: self.queue()
        self.assertEqual(error.exception.code,'image_consent_required')
        self.assertEqual(self.calls,[])

    def test_registered_http_image_path_and_admin_child_restriction(self):
        prefix='/api/platform/v1'
        response=self.a.get(prefix+'/config')
        self.assertTrue(response.json()['image_modes']['live'])
        response=self.a.get('/api/server-admin/v1/session')
        self.assertEqual(response.status_code,403)
        body=dict(request_id=self.rid(),mode='live',purpose='work_cover',learner_id=self.lid,
                  target_id=self.work['id'],target_version=self.work['current_version']['id'],
                  expected_binding_revision=0,slot='cover',prompt='虚构天气作品封面。')
        response=self.a.post(prefix+'/image-jobs',json=body,headers={'Origin':'https://learning.example.test','X-CSRF-Token':self.bootstrap(self.a)['csrf_token']})
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(self.calls,[])


if __name__ == '__main__': unittest.main()
