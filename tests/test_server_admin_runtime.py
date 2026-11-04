"""create_app image binding compatibility and fail-closed deployment defaults."""
from dataclasses import replace
from pathlib import Path
import unittest

from app.server_admin import AdminSettings
from tests.test_learning_v2_identity import Fixture
from tests import test_platform_http as platform_fixture


class AdminImageMainTests(Fixture, unittest.TestCase):
    post = platform_fixture.PlatformHttpTests.post
    provider = platform_fixture.PlatformHttpTests.provider

    def setUp(self):
        platform_fixture.PlatformHttpTests.setUp(self)

    def build(self, *, base=True, secrets=True):
        platform = self.platform_settings if base else replace(self.platform_settings, image_settings=None)
        return self.factory(self.path, core_only=True, learning_settings=self.settings, platform_settings=platform,
            server_admin_settings=AdminSettings(secret_dir=Path(self.tmp.name)/'keys' if secrets else None))

    def test_existing_storage_policy_and_transport_survive_admin_binding(self):
        with self.service.store.transaction() as con:
            before = [tuple(row) for row in con.execute('SELECT * FROM platform_migrations ORDER BY version')]
        app = self.build()
        admin, images = app.state.server_admin, app.state.platform_v1.images
        self.assertIs(admin.image_base, self.image_settings)
        config = admin.image_runtime(self.image_settings)
        self.assertIs(config.transport, self.image_settings.transport)
        self.assertEqual(config.image_consent_versions, self.image_settings.image_consent_versions)
        self.assertIs(admin.images, images)
        self.assertFalse(images.live_available)
        self.assertEqual(config.model, '')
        self.assertEqual(config.image_limit, 0)
        with self.service.store.transaction() as con:
            self.assertEqual(before, [tuple(row) for row in con.execute('SELECT * FROM platform_migrations ORDER BY version')])

    def test_missing_base_uses_private_sibling_with_no_consent_or_budget(self):
        app = self.build(base=False)
        config = app.state.server_admin.image_runtime()
        self.assertEqual(config.storage_dir, Path(self.tmp.name)/'images-private')
        self.assertEqual(config.image_consent_versions, ())
        self.assertEqual(config.image_limit, 0)
        self.assertFalse(config.live_enabled)

    def test_unconfigured_secret_directory_does_not_prevent_startup(self):
        app = self.build(base=False, secrets=False)
        self.assertIsNone(app.state.server_admin.image_runtime().storage_dir)
        self.assertFalse(app.state.platform_v1.images.live_available)


if __name__ == '__main__':
    unittest.main()
