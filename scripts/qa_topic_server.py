"""Isolated, loopback-only topic-selection acceptance server. No paid model calls."""
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from app.main import create_app, digest, now
from tests.test_topic_selection import ranking_for, plan_for
from scripts.run_demo import demo_materials

def screenshot_materials(context):
    result=demo_materials(context)
    for item in result['items']:item['category']='演示资料要点'
    return result


if __name__=='__main__':
    import uvicorn
    folder=Path(sys.argv[1]).resolve()
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'topic-test.sqlite3'
    if path.exists():raise SystemExit('Use a fresh test directory.')
    app=create_app(path,core_only=True,topic_model_runner=ranking_for,core_model_runner=plan_for,materials_model_runner=screenshot_materials)
    users=[{'id':i,'token':'topic-browser-'+i,'name':'选题测试成员'+i} for i in 'ab']
    with closing(sqlite3.connect(path)) as con:
        for index,user in enumerate(users):
            con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at) VALUES(?,?,?,?,?,?,?)',
                        (user['id'],'1800000777'+str(index),user['name'],'合成验收数据','产品设计',digest(user['token']),now()))
        con.commit()
    with TestClient(app) as client:
        h=lambda u:{'Authorization':'Bearer '+u['token']}
        team=client.post('/api/core/teams',json={'name':'连接器选题闭环 · 隔离验收'},headers=h(users[0])).json()
        client.post('/api/core/join',json={'code':team['code']},headers=h(users[1]))
        for user in users:
            connection=client.post('/api/core/teams/'+team['id']+'/connections',json={'label':'MCP 协议验收'},headers=h(user)).json()
            (folder/('binding-'+user['id']+'.json')).write_text(json.dumps({'url':'http://127.0.0.1:'+sys.argv[2],'team_id':team['id'],'token':connection['token']}),encoding='utf-8')
        space=client.get('/api/materials/space?team_id='+team['id'],headers=h(users[0])).json()
        url='/api/materials/spaces/'+space['id']
        source=client.post(url+'/sources',json={'request_id':'topic-materials-fixture','kind':'text','name':'截图清理测试样例','content':'示例活动要求，非正式赛事原文。','nature':'sample'},headers=h(users[0])).json()['source']
        rev=client.get(url,headers=h(users[0])).json()['revision']
        client.post(url+'/sources/'+source['id']+'/parse',json={'expected_revision':rev},headers=h(users[0]))
        rev=client.get(url,headers=h(users[0])).json()['revision']
        client.post(url+'/generate',json={'request_id':'screenshot-fixture-generate','expected_revision':rev},headers=h(users[0]))
    (folder/'fixture.json').write_text(json.dumps({'users':users,'team':team}),encoding='utf-8')
    uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='warning')
