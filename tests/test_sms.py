"""Provider contracts and public configuration status; never sends real SMS."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import sms
from app.main import create_app

CONFIG={'ALIYUN_ACCESS_KEY_ID':'synthetic-key','ALIYUN_ACCESS_KEY_SECRET':'synthetic-secret','ALIYUN_SMS_SIGN_NAME':'test-sign','ALIYUN_SMS_TEMPLATE_CODE':'test-template','ALIYUN_SMS_MODE':'pnvs'}


class SmsTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,CONFIG,clear=True);self.env.start()
    def tearDown(self):
        self.env.stop()
    def test_configured_does_not_claim_delivery(self):
        status=sms.sms_status()
        self.assertTrue(status['configured']);self.assertFalse(status['delivery_verified'])
        self.assertEqual(status['provider'],'aliyun-pnvs')
        self.assertNotIn('synthetic',json.dumps(status))
    def test_unknown_mode_cannot_silently_send_to_wrong_provider(self):
        os.environ['ALIYUN_SMS_MODE']='typo'
        self.assertFalse(sms.cloud_sms_ready());self.assertFalse(sms.sms_status()['configured'])
    def test_missing_template_is_reported_without_private_values(self):
        del os.environ['ALIYUN_SMS_TEMPLATE_CODE']
        status=sms.sms_status();self.assertFalse(status['configured']);self.assertIn('赠送模板 CODE',status['missing'])
    def test_pnvs_uses_same_code_as_local_verifier(self):
        with patch('app.sms._signed_get',return_value={'Code':'OK','Success':True}) as request:
            self.assertTrue(sms.deliver_login_code('18000000000','123456')[0])
        host,version,body=request.call_args.args
        self.assertEqual(host,'dypnsapi.aliyuncs.com');self.assertEqual(body['Action'],'SendSmsVerifyCode')
        self.assertEqual(json.loads(body['TemplateParam'])['code'],'123456');self.assertEqual(body['ReturnVerifyCode'],'false')
    def test_enterprise_selects_classic_endpoint(self):
        os.environ['ALIYUN_SMS_MODE']='enterprise'
        with patch('app.sms._signed_get',return_value={'Code':'OK'}) as request:
            self.assertTrue(sms.deliver_login_code('18000000000','123456')[0])
        self.assertEqual(request.call_args.args[0],'dysmsapi.aliyuncs.com')
    def test_known_errors_are_useful_and_unknown_messages_are_private(self):
        for code,expected in [('SignatureDoesNotMatch','凭据'),('Forbidden.RAM','权限'),('isv.AMOUNT_NOT_ENOUGH','余额'),('isv.SMS_TEMPLATE_ILLEGAL','模板'),('isv.BUSINESS_LIMIT_CONTROL','频繁')]:
            with self.subTest(code=code),patch('app.sms._signed_get',return_value={'Code':code,'Message':'secret-do-not-echo'}):
                sent,notice=sms.deliver_login_code('18000000000','123456')
                self.assertFalse(sent);self.assertIn(expected,notice);self.assertNotIn('secret',notice)
        self.assertNotIn('secret',sms.provider_failure({'Code':'unknown','Message':'secret'}))
    def test_http_error_body_preserves_provider_error_code(self):
        error=urllib.error.HTTPError('https://example.invalid',403,'forbidden',{},io.BytesIO(b'{"Code":"Forbidden.RAM"}'))
        with patch('urllib.request.urlopen',side_effect=error):
            self.assertEqual(sms._signed_get('dypnsapi.aliyuncs.com','2017-05-25',{})['Code'],'Forbidden.RAM')
    def test_array_response_is_not_interpreted_as_success(self):
        response=unittest.mock.MagicMock();response.__enter__.return_value.read.return_value=b'[]'
        with patch('urllib.request.urlopen',return_value=response):
            self.assertIsNone(sms._signed_get('dypnsapi.aliyuncs.com','2017-05-25',{}))
    def test_public_status_works_in_core_mode_and_failed_send_issues_no_code(self):
        with tempfile.TemporaryDirectory() as directory,TestClient(create_app(Path(directory)/'sms.sqlite3',core_only=True)) as client:
            status=client.get('/api/studio/sms-status');self.assertEqual(status.status_code,200)
            self.assertTrue(status.json()['configured']);self.assertNotIn('synthetic',status.text)
            with patch('app.sms.send_pnvs_code',return_value=(False,'短信余额不足')):
                response=client.post('/api/studio/codes',json={'phone':'18000000000'})
            self.assertEqual(response.status_code,503);self.assertNotIn('"code": "123456"',response.text)
            with patch('app.sms.send_pnvs_code',return_value=(True,'aliyun-pnvs')):
                response=client.post('/api/studio/codes',json={'phone':'18000000000'})
            self.assertEqual(response.status_code,200);self.assertNotIn('code',response.json())
