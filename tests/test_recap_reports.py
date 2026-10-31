import json
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.planner import PlannerError
from tests import test_team_core as fixtures


class RecapReportTests(unittest.TestCase):
    tearDown=fixtures.CoreTests.tearDown
    report=fixtures.CoreTests.report
    def setUp(self):
        fixtures.CoreTests.setUp(self)
        self.client.close();self.calls=[];self.bad=False;self.fail=False
        def model(context):
            self.calls.append(context)
            if self.fail:raise PlannerError("model_timeout","模型超时，感悟保留。",504)
            return {'summary':'孩子在本次项目中尝试设计。','observations':[{'title':'本场观察','text':'依据本人记录，主动思考交互问题；仍需下一次实践验证。','source_ids':['not-a-source' if self.bad else 'reflection']}],'next_steps':['下一次先找同伴试用。'],'limitations':['比赛结果为本人填写，尚未核实。']}
        self.app=create_app(self.path,core_only=True,recap_model_runner=model)
        self.client=TestClient(self.app);self.url=self.base+'/recap'
    def save(self,version=0):
        r=self.client.put(self.url,headers=self.h('a'),json={'expected_version':version,'feelings':'我发现沟通比写代码更难。','ideas':'下次想先访谈用户。','result':'完成展示，名次尚未公布。'})
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def generate(self,key='report-request-1',version=1):
        r=self.client.post(self.url+'/reports',headers=self.h('a'),json={'request_id':key,'expected_version':version})
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def share(self,ident):
        return self.client.post(self.url+'/reports/'+ident+'/share',headers=self.h('a'),json={'confirmed':True})
    def test_private_reflection_and_only_own_work_enter_context(self):
        self.save();self.report(event='own',summary='本人设计记录')
        self.report(headers=self.h('b'),event='peer',summary='队友私人工作标记')
        report=self.generate();self.assertEqual(report['status'],'ready')
        context=json.dumps(self.calls[0],ensure_ascii=False)
        self.assertIn('本人设计记录',context);self.assertNotIn('队友私人工作标记',context)
        peer=self.client.get(self.url,headers=self.h('b')).json()
        self.assertEqual(peer['version'],0);self.assertEqual(peer['reports'],[])
        self.assertEqual(self.client.post(self.url+'/reports/'+report['id']+'/share',headers=self.h('b'),json={'confirmed':True}).status_code,404)
    def test_saved_draft_reuse_and_broken_citations_rejected(self):
        self.save();one=self.generate();two=self.generate()
        self.assertEqual(one['id'],two['id']);self.assertEqual(len(self.calls),1)
        self.bad=True;bad=self.generate('new-report-request')
        self.assertEqual(bad['status'],'failed');self.assertEqual(bad['body'],{})
        self.assertEqual(self.client.get(self.url,headers=self.h('a')).json()['version'],1)
    @patch.dict('os.environ',{'PUBLIC_BASE_URL':'https://songban.example'})
    def test_parent_reads_summary_qr_and_revocation_and_restart(self):
        self.save();self.report(event='private',summary='不应在家长页原样出现的原文')
        report=self.generate();r=self.share(report['id']);self.assertEqual(r.status_code,200,r.text)
        share=r.json();path=share['url'].replace('https://songban.example','')
        page=self.client.get(path);self.assertEqual(page.status_code,200)
        self.assertIn('本次项目',page.text);self.assertNotIn('不应在家长页原样出现',page.text)
        self.assertIn('no-store',page.headers['cache-control'])
        qr=self.client.get(share['qr_url']);self.assertEqual(qr.status_code,200);self.assertIn('<svg',qr.text)
        with TestClient(create_app(self.path,core_only=True)) as reopened:self.assertEqual(reopened.get(path).status_code,200)
        self.assertEqual(self.client.delete(self.url+'/reports/'+report['id']+'/share',headers=self.h('a')).status_code,200)
        self.assertEqual(self.client.get(path).status_code,404);self.assertEqual(self.client.get(share['qr_url']).status_code,404)
    @patch.dict('os.environ',{'PUBLIC_BASE_URL':'https://songban.example'})
    def test_updated_reflection_must_regenerate_and_expiry(self):
        self.save();report=self.generate();share=self.share(report['id']).json()
        self.save(1);self.assertEqual(self.share(report['id']).status_code,409)
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("UPDATE recap_shares SET expires_at='2000-01-01T00:00:00+00:00'");con.commit()
        self.assertEqual(self.client.get(share['qr_url']).status_code,404)
    @patch.dict('os.environ',{'PUBLIC_BASE_URL':'http://127.0.0.1:8890'})
    def test_loopback_qr_is_not_presented_as_phone_accessible(self):
        self.save();report=self.generate();r=self.share(report['id'])
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['error']['code'],'share_address_required')
    def test_no_auth_and_stale_save(self):
        self.assertEqual(self.client.get(self.url).status_code,401)
        self.save()
        r=self.client.put(self.url,headers=self.h('a'),json={'expected_version':0,'feelings':'另一份','result':'未知'})
        self.assertEqual(r.status_code,409)

    def test_failed_model_preserves_reflection_and_never_replays_same_request(self):
        self.save();self.fail=True
        one=self.generate();two=self.generate()
        self.assertEqual(one['status'],'failed');self.assertEqual(one['id'],two['id']);self.assertEqual(len(self.calls),1)
        saved=self.client.get(self.url,headers=self.h('a')).json()
        self.assertEqual(saved['reflection']['feelings'],'我发现沟通比写代码更难。')
