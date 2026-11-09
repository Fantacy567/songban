"""Course-series main registration, catalogue images and old-route compatibility.

All records are synthetic. No listeners, private config or model calls.
"""
from dataclasses import replace
import hashlib
import unittest
import xml.etree.ElementTree as ET

from tests import test_platform_http as baseline
from tests.test_learning_v2_identity import Fixture


class LearningCourseIntegrationTests(Fixture, unittest.TestCase):
    post = baseline.PlatformHttpTests.post
    provider = baseline.PlatformHttpTests.provider

    def setUp(self):
        baseline.PlatformHttpTests.setUp(self)
        self.settings = replace(self.settings, course_enabled=True)
        self.app = self.factory(self.path, core_only=True, learning_settings=self.settings,
            platform_settings=replace(self.platform_settings, navigation_enabled=True,
                                      creative_studio_enabled=True))
        self.service = self.app.state.learning_v2
        self.service.clock = lambda: self.now[0]
        self.a, self.b = self.client(), self.client()
        self.login(self.a, 'parent-a')
        self.enter(self.a, self.lid)

    def test_main_catalog_has_seven_distinct_images_and_readable_details(self):
        response = self.b.get('/api/platform/v1/learning-catalog')
        self.assertEqual(response.status_code, 200, response.text)
        courses = response.json()['courses']
        expected = ['ai-tools', 'imagination', 'first-project', 'plugins',
                    'models', 'api', 'model-powered-app']
        self.assertEqual([c['id'] for c in courses], expected)
        self.assertEqual([c['chapter']['id'] for c in courses], ['tools']*4+['advanced']*3)
        hashes = set()
        for course in courses:
            self.assertEqual(course['status'], 'trial')
            self.assertTrue(course['cover']['alt'])
            result = self.b.get('/api/platform/v1/learning-catalog/'+course['id'])
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['id'], course['id'])
            asset = self.b.get(course['cover']['src'])
            self.assertEqual(asset.status_code, 200, course['cover']['src'])
            self.assertIn('image/svg+xml', asset.headers['content-type'])
            image = ET.fromstring(asset.content)
            self.assertEqual(image.attrib['viewBox'], '0 0 900 600')
            self.assertIsNone(image.find('.//{http://www.w3.org/2000/svg}script'))
            hashes.add(hashlib.sha256(asset.content).hexdigest())
        self.assertEqual(len(hashes), 7)

    def test_new_progress_routes_share_identity_and_leave_old_course_readable(self):
        for course in ('ai-tools', 'imagination'):
            response = self.a.get('/api/platform/v1/learning-courses/'+course+'/progress')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['revision'], 0)
            self.assertEqual(response.json()['status'], 'not_started')
            self.assertEqual(self.b.get('/api/platform/v1/learning-courses/'+course+'/progress').status_code, 401)
        self.assertEqual(self.b.get('/api/learning/v2/courses').status_code, 200)
        self.assertEqual(self.b.get('/api/platform/v1/config').status_code, 200)
        self.assertEqual(self.b.get('/learning-prep').status_code, 200)
        self.assertEqual(self.b.get('/').status_code, 200)
        with self.service.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM creative_calls').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
