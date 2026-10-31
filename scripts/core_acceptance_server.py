"""Isolated acceptance service: synthetic users, separate database, explicit model substitute."""
import argparse
import json
import secrets
import sqlite3
import sys
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.main import create_app, digest, now
from app.studio import hash_password
from app.private_files import restrict_file
import uvicorn


def fixture_plan(context):
    members=context['members'];reports=context['reports'];sources=[r['id'] for r in reports] or ['direction']
    return {'summary':'协议测试：对照两名成员提供的观点，先验证接口，再让页面接入。此回复不是来自真实模型。','findings':[{'topic':'接口是否已经可用','decision':'保留双方报告，先检查真实请求结果。','reason':'后端说代码写好，前端仍未收到；两者都不能证明已联调成功。','source_ids':sources[:2],'needs_check':True}], 'tasks':[{'key':'T1','title':'验证接口并提供调用示例','owner_id':members[0]['id'],'acceptance':'正常与空输入各发一次请求，提供返回内容','depends_on':[],'source_ids':sources[:1]},{'key':'T2','title':'将页面接到已验证接口','owner_id':members[-1]['id'],'acceptance':'在页面提交并显示真实结果','depends_on':['T1'],'source_ids':sources[-1:]}], 'questions':['还缺接口实际验证结果。']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dir',required=True);parser.add_argument('--port',type=int,default=8888);parser.add_argument('--skill-home');parser.add_argument('--plugin-home');args=parser.parse_args()
    root=Path(args.dir);root.mkdir(parents=True,exist_ok=True)
    if args.skill_home:
        import app.team_core as core
        from functools import partial
        core.install_connector_skill=partial(core.install_connector_skill,home=args.skill_home)
    if args.plugin_home:
        import app.team_core as core
        from functools import partial
        core.install_connector_plugin=partial(core.install_connector_plugin,home=args.plugin_home)
    app=create_app(root/'acceptance.sqlite3',core_only=True,core_model_runner=fixture_plan)
    @app.get('/api/core-audit-fixture')
    def audit_marker():
        return {'isolated':True,'model':'fixture'}
    credentials=[]
    with closing(sqlite3.connect(root/'acceptance.sqlite3')) as con:
        for n,name in enumerate(['后端验收成员','前端验收成员']):
            token=secrets.token_urlsafe(24);ident='acceptance-'+str(n);password='acceptance-'+secrets.token_hex(8);phone='1800000010'+str(n)
            con.execute('INSERT OR REPLACE INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',(ident,phone,name,'隔离功能验收','后端' if n==0 else '前端',digest(token),now(),hash_password(password)))
            credentials.append({'id':ident,'phone':phone,'password':password,'token':token})
        con.commit()
    file=root/'private-fixture.json';file.write_text(json.dumps(credentials),encoding='utf-8');restrict_file(file)
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')
