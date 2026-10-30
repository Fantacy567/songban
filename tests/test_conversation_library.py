"""Evidence archive: full replies, identity, scoped retrieval, durability and task separation."""
import json
import sqlite3
from contextlib import closing
from fastapi.testclient import TestClient
import unittest
from tests import test_team_core as fixture
from app.main import create_app,now


class LibraryTests(unittest.TestCase):
    setUp=fixture.CoreTests.setUp
    tearDown=fixture.CoreTests.tearDown
    conn=fixture.CoreTests.conn
    report=fixture.CoreTests.report
    snap=fixture.CoreTests.snap
    review=fixture.CoreTests.review
    confirm=fixture.CoreTests.confirm
    # Inherit only the fixture helpers, not every unrelated regression case.
    def put(self,user='a',event='turn',**extra):
        body={'selected':True,'event_id':event,'user_message':'我是设计师','assistant_summary':'先画首页','assistant_message':'好的，您是设计师。先画出主要流程。','full_reply_authorized':True,'model_name':'fixture-model','conversation_stage':'discussion',**extra}
        if body.get('assistant_message') is None:body.pop('assistant_message',None)
        return self.client.post(self.base+'/conversation-notes',headers=self.h(user),json=body)
    def test_full_reply_consent_identity_and_restart(self):
        denied=self.put(full_reply_authorized=False);self.assertEqual(denied.status_code,422)
        text='完整回复，包含可见的说明段落和最终答案。'*1000
        r=self.put(assistant_message=text);self.assertEqual(r.status_code,200,r.text);ident=r.json()['note_id']
        brief=self.client.get(self.base+'/library?brief=true',headers=self.h('b')).json()['items'][0]
        self.assertEqual(brief['source_kind'],'manual');self.assertEqual(brief['source_label'],'网页手动补充');self.assertEqual(brief['author_id'],'a');self.assertEqual(brief['author'],'后端测试成员');self.assertTrue(brief['content_truncated']);self.assertNotIn('assistant_message',brief['report'])
        self.assertEqual(brief['reply_kind'],'full');self.assertEqual(brief['reply_length'],len(text))
        with TestClient(create_app(self.path,core_only=True)) as restarted:
            saved=restarted.get(self.base+'/library/'+ident,headers=self.h('b')).json()
            self.assertEqual(saved['report']['assistant_message'],text)
            self.assertEqual(saved['report']['model_name'],'fixture-model');self.assertEqual(saved['report']['user_name'],'后端测试成员')
        self.assertEqual(self.put(event='bad-name',user_name='伪造').status_code,422)
    def test_chat_cannot_complete_or_reset_a_task_and_dedup_survives_stage_change(self):
        first=self.put();self.assertEqual(first.status_code,200)
        self.confirm(self.review())
        repeat=self.put();self.assertTrue(repeat.json()['duplicate']);self.assertEqual(first.json()['note_id'],repeat.json()['note_id'])
        self.assertEqual(self.client.get(self.base+'/library/'+first.json()['note_id'],headers=self.h('a')).json()['stage'],'discussion')
        self.assertEqual(self.report(event='real-task-report',task_key='T1',plan_version=1,status='reported_done',evidence=['真实检查依据']).status_code,200)
        prior=self.snap()['active_plan']['tasks'][0]['latest_report_id']
        chat=self.put(event='during-task',task_key='T1',plan_version=1,status='reported_done',conversation_stage='development')
        self.assertEqual(chat.status_code,200,chat.text)
        task=self.snap()['active_plan']['tasks'][0];self.assertEqual(task['latest_report_id'],prior);self.assertEqual(task['status'],'reported_done')
        self.assertEqual(self.put(event='other-task',task_key='T2',plan_version=1).status_code,409)
    def test_full_archive_does_not_bloat_team_model_context(self):
        self.put(assistant_message='原文数据'*12000)
        snap=self.snap();self.assertNotIn('assistant_message',snap['reports'][0]);self.assertTrue(snap['reports'][0]['has_full_reply'])
        self.assertEqual(snap['library_stats']['total'],1);self.assertIsNone(snap['proposal'])
    def test_old_summary_is_not_labelled_full(self):
        self.put(assistant_message=None,event='summary-only')
        result=self.client.get(self.base+'/library',headers=self.h('b')).json()['items'][0]
        self.assertEqual(result['reply_kind'],'summary');self.assertEqual(result['reply_preview'],'先画首页')
    def test_library_beyond_old_120_limit_is_searchable_and_pageable(self):
        with closing(sqlite3.connect(self.path)) as con:
            for i in range(145):
                ident='archive-'+str(i);user='a' if i%2 else 'b';payload={'summary':'needle' if i==0 else '讨论','user_message':'早期用户原话 '+str(i),'assistant_summary':'回复要点','model_name':'fixture-model','recorded_stage':'development' if i%2 else 'discussion','task_key':'T1' if i%2 else '', 'plan_version':1 if i%2 else 0}
                con.execute('INSERT INTO core_reports(id,squad_id,user_id,connection_id,event_id,payload_hash,body,created_at) VALUES(?,?,?,?,?,?,?,?)',(ident,self.sid,user,'seed',ident,'seed',json.dumps(payload),now()))
                con.execute('INSERT INTO library_notes(id,squad_id,author_id,body,suggestion,created_at) VALUES(?,?,?,?,?,?)',(ident,self.sid,user,'needle' if i==0 else '讨论','seed',now()))
            con.commit()
        ids=[];cursor=None
        while True:
            r=self.client.get(self.base+'/library',params={'limit':20,**({'cursor':cursor} if cursor else {})},headers=self.h('a')).json();ids.extend(n['id'] for n in r['items']);cursor=r['next_cursor']
            self.assertEqual(r['total'],145)
            if cursor is None:break
        self.assertEqual(len(ids),145);self.assertEqual(len(set(ids)),145)
        found=self.client.get(self.base+'/library?q=needle',headers=self.h('b')).json();self.assertEqual(found['items'][0]['id'],'archive-0')
        self.assertEqual(self.client.get(self.base+'/library?author_id=a&stage=development&task_key=T1',headers=self.h('a')).json()['total'],72)
        self.assertEqual(self.client.get(self.base+'/library?q=%25',headers=self.h('a')).json()['total'],0)
    def test_full_text_search_and_team_boundaries(self):
        r=self.put(assistant_message='只有完整回复中才有的线索：水獭');ident=r.json()['note_id']
        self.assertEqual(self.client.get(self.base+'/library?q=水獭',headers=self.h('b')).json()['total'],1)
        self.assertEqual(self.client.get(self.base+'/library',headers=self.h('c')).status_code,403)
        other=self.client.post('/api/core/teams',json={'name':'另一队'},headers=self.h('c')).json()['id']
        self.assertEqual(self.client.get('/api/core/teams/'+other+'/library/'+ident,headers=self.h('c')).status_code,404)
        conn=self.conn();h={'Authorization':'Bearer '+conn['token']}
        self.assertEqual(self.client.get(self.base+'/library',headers=h).status_code,200)
        self.client.patch(self.base+'/connections/'+conn['id'],json={'action':'revoke'},headers=self.h('a'))
        self.assertEqual(self.client.get(self.base+'/library',headers=h).status_code,401)
    def test_filters_and_oversize_are_not_silently_accepted(self):
        for suffix in ['?limit=51','?cursor=0','?stage=unknown','?q='+'x'*201]:self.assertEqual(self.client.get(self.base+'/library'+suffix,headers=self.h('a')).status_code,422)
        self.assertEqual(self.put(assistant_message='x'*60001).status_code,422)
