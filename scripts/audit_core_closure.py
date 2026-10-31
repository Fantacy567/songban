"""Reproducible audit probes. Synthetic records, temporary SQLite, explicit model fixtures."""
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from app.main import create_app,digest,now
from tests.test_team_core import plan_for
from tests.test_materials import fixture_model


def run():
    evidence={}
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'audit.sqlite3'
        app=create_app(path,core_only=True,core_model_runner=plan_for,materials_model_runner=fixture_model)
        with closing(sqlite3.connect(path)) as con:
            for ident in ('a','b'):
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at) VALUES(?,?,?,?,?,?,?)',(ident,'1880000099'+str(ident=='b'),'合成测试'+ident,'仅隔离测试','验证',digest('audit-'+ident),now()))
            con.commit()
        headers=lambda p:{'Authorization':'Bearer audit-'+p}
        with TestClient(app) as c:
            def call(method,url,body=None,who='a',expected=200):
                r=c.request(method,url,headers=headers(who),json=body)
                assert r.status_code==expected,(url,r.status_code,r.text)
                return r.json() if r.headers.get('content-type','').startswith('application/json') else r.text
            team=call('POST','/api/core/teams',{'name':'闭环合成测试'});base='/api/core/teams/'+team['id']
            call('POST','/api/core/join',{'code':team['code']},'b')
            snap=lambda:call('GET',base)
            call('PUT',base+'/direction',{'goal':'验证两人协作闭环','rules':'提交可运行作品','rubric':'可操作可检查','expected_revision':snap()['revision']})
            proposal=call('POST',base+'/review',{})
            evidence['before_confirmation']={'plan_version':snap()['plan_version'],'tasks':snap()['active_plan'].get('tasks',[])}
            call('POST',base+'/proposals/'+proposal['proposal_id']+'/confirm',{'expected_revision':proposal['base_revision']})
            def report(task,who,event):
                return call('POST',base+'/reports',{'event_id':event,'task_key':task,'plan_version':snap()['plan_version'],'status':'reported_done','summary':'合成成果已提交','evidence':['合成测试：正常及错误输入验证记录'],'tool':'闭环测试','origin':'human'},who)
            def check(task,who,verdict='accepted'):
                s=snap();t=next(t for t in s['active_plan']['tasks'] if t['key']==task)
                return call('POST',base+'/tasks/'+task+'/check',{'expected_revision':s['revision'],'plan_version':s['plan_version'],'report_id':t['latest_report_id'],'verdict':verdict,'note':'合成测试：核对正常和错误输入。'},who)
            report('T1','a','first');check('T1','b','changes_requested');report('T1','a','revised');check('T1','b')
            report('T2','b','second');check('T2','a')
            completed=snap()
            evidence['two_person_loop']={'accepted':completed['workflow']['accepted_tasks'],'total':completed['workflow']['total_tasks'],'all_checked':completed['workflow']['all_handoffs_checked'],'next_action':completed['workflow']['next_action'],'official_receipt':next(i for i in completed['workflow']['checks'] if i['key']=='submission')}
            export=call('GET',base+'/handoff.md');evidence['handoff_export']={'contains_both_tasks':all(x in export for x in ('T1','T2')),'truthful_submission_notice':'没有读取主办方收件状态' in export}
            call('POST',base+'/reports',{'event_id':'reflection','tool':'网页复盘','origin':'human','status':'discussion','summary':'复盘：合成测试已验证退回和再次提交。'})
            evidence['reflection_is_shared_report']=any(r['summary'].startswith('复盘：') for r in call('GET',base,who='b')['reports'])
            with TestClient(create_app(path,core_only=True)) as reopened:
                s=reopened.get(base,headers=headers('b')).json()
                evidence['core_restart_persistence']={'all_checked':s['workflow']['all_handoffs_checked'],'reports':len(s['reports'])}
            # A one-member team is allowed, but the acceptance policy requires a second human.
            solo=call('POST','/api/core/teams',{'name':'单人闭环测试'});solo_base='/api/core/teams/'+solo['id']
            ss=call('GET',solo_base)
            call('PUT',solo_base+'/direction',{'goal':'单人作品','rules':'允许单人','expected_revision':ss['revision']})
            p=call('POST',solo_base+'/review',{});call('POST',solo_base+'/proposals/'+p['proposal_id']+'/confirm',{'expected_revision':p['base_revision']})
            call('POST',solo_base+'/reports',{'event_id':'solo-done','task_key':'T1','plan_version':1,'status':'reported_done','summary':'已完成合成成果','evidence':['合成检查记录']})
            ss=call('GET',solo_base);t=ss['active_plan']['tasks'][0]
            r=c.post(solo_base+'/tasks/T1/check',headers=headers('a'),json={'expected_revision':ss['revision'],'plan_version':1,'report_id':t['latest_report_id'],'verdict':'accepted','note':'本人检查'})
            evidence['single_member_block']={'members':len(ss['members']),'self_check_http':r.status_code,'error':r.json(),'next_action':ss['workflow']['next_action']}
            # No-model branch preserves existing records but offers no manual proposal route.
            with patch('app.team_core.team_model_config',return_value={'api_key':''}),TestClient(create_app(path,core_only=True)) as no_model:
                # Change evidence to invalidate the earlier fixture proposal, then review.
                call('POST',solo_base+'/reports',{'event_id':'fresh-input','summary':'新进展用于使旧草案过期'})
                r=no_model.post(solo_base+'/review',headers=headers('a'),json={})
                evidence['no_model']={'http':r.status_code,'error':r.json()}
            # Material draft carries old text after the source item was corrected.
            personal=call('GET','/api/materials/space');mb='/api/materials/spaces/'+personal['id']
            src=call('POST',mb+'/sources',{'request_id':'audit-source-1','kind':'text','name':'合成规则','content':'提交时间尚未确认。','nature':'sample'})['source']
            call('POST',mb+'/sources/'+src['id']+'/parse',{'expected_revision':call('GET',mb)['revision']})
            call('POST',mb+'/generate',{'request_id':'audit-generate-1','expected_revision':call('GET',mb)['revision']})
            ms=call('GET',mb);item=ms['result']['items'][0]
            d=call('POST',mb+'/drafts',{'request_id':'audit-draft-1','expected_revision':ms['revision'],'team_id':team['id'],'item_ids':[item['id']],'kind':'direction','share_sources':True})
            call('PATCH',mb+'/items/'+item['id'],{'expected_revision':call('GET',mb)['revision'],'text':'人工纠正：原条目不再可用，请勿使用旧草稿。','verification':'human_confirmed','note':'审核测试纠正'})
            prepared=call('POST',mb+'/drafts/'+d['id']+'/prepare',{'expected_revision':call('GET',mb)['revision']},expected=409)
            evidence['old_draft_after_human_edit']={'prepare_http':409,'error':prepared['error'],'draft_text':d['body']['text'],'current_text':call('GET',mb)['result']['items'][0]['text']}
            ts=call('GET','/api/materials/space?team_id='+team['id'],who='b')
            evidence['new_team_material_space']={'saved_drafts':len(ts['drafts']),'has_model_result':bool(ts['result'].get('items')),'sources':len(ts['sources'])}
            tmb='/api/materials/spaces/'+ts['id']
            call('POST',tmb+'/generate',{'request_id':'team-generate-1','expected_revision':ts['revision']})
            ts=call('GET',tmb);ti=ts['result']['items'][0]
            td=call('POST',tmb+'/drafts',{'request_id':'team-draft-1','expected_revision':ts['revision'],'team_id':team['id'],'item_ids':[ti['id']],'kind':'direction','share_sources':True})
            call('PATCH',tmb+'/items/'+ti['id'],{'expected_revision':call('GET',tmb)['revision'],'text':'同团队人工纠正：请勿使用旧条目','verification':'human_confirmed','note':'同一团队空间内纠正'})
            tp=call('POST',tmb+'/drafts/'+td['id']+'/prepare',{'expected_revision':call('GET',tmb)['revision']},expected=409)
            evidence['same_team_draft_after_human_edit']={'prepare_http':409,'error':tp['error'],'draft_text':td['body']['text'],'current_text':call('GET',tmb)['result']['items'][0]['text'],'same_space':td['body']['source_space']==ts['id']}
            # The route catalog is evidence of what is implemented, not guesses at unavailable URLs.
            paths=sorted(app.openapi()['paths'])
            evidence['route_inventory']={'core':[p for p in paths if p.startswith('/api/core/')],'materials':[p for p in paths if p.startswith('/api/materials/')],'reports_modules_present':(ROOT/'app/reports.py').exists()}
    return evidence


if __name__=='__main__':
    output=Path(os.environ.get('SONGBAN_AUDIT_OUTPUT',str(ROOT/'.browser-cache/materials/fixes-20261031')))/'core-closure.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    result=run();output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='route_inventory'},ensure_ascii=False,indent=2))
