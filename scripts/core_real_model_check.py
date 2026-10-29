"""One bounded real team-model call on synthetic acceptance data; no credential output."""
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import create_app, digest, now

out=Path(__file__).resolve().parent.parent/'docs/core-collaboration/evidence/real_model_check.json'
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'real-check.sqlite3'
    app=create_app(path,core_only=True)
    with closing(sqlite3.connect(path)) as con:
        for ident,name,skills in [('a','后端验收成员','Python接口'),('b','前端验收成员','页面开发')]:
            con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at) VALUES(?,?,?,?,?,?,?)',(ident,'1800000020'+str(ident=='b'),name,'合成验收数据，非真实成员隐私',skills,digest('real-check-'+ident),now()))
        con.commit()
    h=lambda x:{'Authorization':'Bearer real-check-'+x}
    with TestClient(app) as c:
        team=c.post('/api/core/teams',json={'name':'真实模型单次验收（合成数据）'},headers=h('a')).json();base='/api/core/teams/'+team['id']
        c.post('/api/core/join',json={'code':team['code']},headers=h('b'))
        rev=c.get(base,headers=h('a')).json()['revision']
        c.put(base+'/direction',headers=h('a'),json={'goal':'完成姓名介绍接口与网页提交展示，两人联调。','rules':'本轮开发验收，非官方赛规：能操作并展示实际结果。','rubric':'完整、准确、可检查。','non_goals':'不做账号系统和素材库。','expected_revision':rev})
        for who,position in [('a','接口代码已写，但没有真实请求验证'),('b','页面准备好了，尚未拿到可用接口')]:
            c.post(base+'/reports',headers=h(who),json={'event_id':'acceptance-'+who,'tool':'个人工具自报（合成验收输入）','summary':position,'views':[{'topic':'接口可用性','position':position}]})
        r=c.post(base+'/review',json={},headers=h('a'))
        result={'date':now(),'attempts':1,'input':'仅合成验收数据','status_code':r.status_code,'paid_model':True}
        if r.status_code==200:
            data=r.json();snap=c.get(base,headers=h('a')).json()
            result.update({'source':data['provenance'],'model_id':snap['proposal']['model_id'],'summary':data['body']['summary'],'findings':data['body']['findings'],'task_count':len(data['body']['tasks']),'plan_not_auto_published':snap['plan_version']==0})
        else:result['error']=r.json().get('error',{})
        out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
        sys.exit(0 if r.status_code==200 else 1)
