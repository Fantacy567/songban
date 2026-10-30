"""Explicit live verification with synthetic inputs or the authorized plan; no account data."""
import base64
import json
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from app.main import create_app,digest,now
from app.planner import team_model_config
from app import materials

if __name__=='__main__':
    folder=ROOT/'.browser-cache'/'materials';folder.mkdir(parents=True,exist_ok=True)
    planning='--planning' in sys.argv
    prefix='live-planning' if planning else 'live'
    cfg=team_model_config()
    if not cfg.get('api_key'):
        print('Live model not configured; no request sent.');sys.exit(2)
    db=folder/('live-'+uuid.uuid4().hex[:8]+'.sqlite3')
    app=create_app(db,core_only=True)
    # Observe the real adapter response to diagnose protocol failures; do not substitute a model.
    real_request=materials.request_materials_model
    def observed_request(context):
        output,model=real_request(context)
        (folder/(prefix+'-raw-output.json')).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        return output,model
    materials.request_materials_model=observed_request
    token='local-live-qa-'+uuid.uuid4().hex
    with closing(sqlite3.connect(db)) as con:
        con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at) VALUES(?,?,?,?,?,?,?)',('live-qa','18800009993','本机合成资料验证','合成测试','测试',digest(token),now()));con.commit()
    h={'Authorization':'Bearer '+token}
    with TestClient(app) as c:
        space=c.get('/api/materials/space',headers=h).json()['id'];base='/api/materials/spaces/'+space
        sources=[{'kind':'text','name':'虚构通知与聊天','nature':'sample','content':'以下均为虚构测试材料。活动日期：2026年11月7日至8日。教育主题，支持1至3人组队。必须提交可运行作品链接和项目说明，完成3分钟展示。正式提交截止时间、年龄资格与评分比例尚未提供。聊天：小林说愿意做演示，小李说愿意做设计，分工未经团队确认。'}, {'kind':'text','name':'另一份未核实通知','nature':'sample','content':'虚构材料：支持4至5人组队。请向主办方核对人数，不知道哪份通知有效。'}]
        image=folder/'screenshot.png'
        if image.exists():sources.append({'kind':'file','name':'真实OCR合成截图.png','nature':'sample','content':base64.b64encode(image.read_bytes()).decode()})
        if planning:
            sources=[{'kind':'text','name':'用户授权的统一资料入口功能规划（原文）','nature':'unverified','content':(ROOT/'docs/planning/统一资料入口-功能规划.md').read_text(encoding='utf-8')}]
        for body in sources:
            r=c.post(base+'/sources',headers=h,json={**body,'request_id':uuid.uuid4().hex});r.raise_for_status();sid=r.json()['source']['id']
            revision=c.get(base,headers=h).json()['revision']
            c.post(base+'/sources/'+sid+'/parse',headers=h,json={'expected_revision':revision}).raise_for_status()
        revision=c.get(base,headers=h).json()['revision']
        r=c.post(base+'/generate',headers=h,json={'request_id':uuid.uuid4().hex,'expected_revision':revision})
        snapshot=c.get(base,headers=h).json()
    evidence={'model_id':cfg.get('model_id'),'http_status':r.status_code,'response':r.json(),'source_statuses':[{k:s[k] for k in ('id','status','error')} for s in snapshot['sources']],'provenance':'real server-configured model; authorized planning document' if planning else 'real server-configured model; synthetic inputs with actual local OCR','private_account_data_used':False}
    (folder/(prefix+'-result.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'http_status':r.status_code,'model_id':cfg.get('model_id'),'state':r.json().get('status'),'error':r.json().get('error'),'item_count':len(snapshot['result'].get('items',[]))},ensure_ascii=False))
