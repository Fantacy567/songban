"""Isolated loopback task-board fixture; SMS and model are explicit test doubles."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.main import create_app
from tests.test_team_core import plan_for
import uvicorn
import os

def recap_fixture(context):
    return {'summary':'本次孩子完成了首页设计，并反思了沟通问题。','observations':[{'title':'愿意反思合作','text':'本人提到沟通困难，并提出下次提前交流；仍需后续实践验证。','source_ids':['reflection']}],'next_steps':['下次先邀请同伴试用草图。'],'limitations':['比赛结果为本人填写，尚未核实。']}

def board_plan(context):
    plan=plan_for(context)
    plan['tasks']=[
        {'key':'T1','title':'画出首页草图','owner_id':context['members'][0]['id'],'acceptance':'上传可查看的草图，队友能理解流程','depends_on':[],'source_ids':['direction']},
        {'key':'T2','title':'完成交互说明','owner_id':context['members'][0]['id'],'acceptance':'说明按钮操作后的页面变化','depends_on':[],'source_ids':['direction']},
        {'key':'T3','title':'实现首页','owner_id':context['members'][1]['id'],'acceptance':'按草图实现可运行页面','depends_on':['T1'],'source_ids':['direction']},
    ]
    return plan

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='songban-task-board-') as tmp,patch('app.studio.must_deliver',return_value=False),patch('app.studio.test_codes_allowed',return_value=True),patch('app.studio.deliver_login_code',return_value=(False,'本机测试，不发送短信')),patch('app.team_core.team_model_config',return_value={'api_key':'','model_id':'协议测试'}):
        os.environ['PUBLIC_BASE_URL']='http://10.10.10.10:8894'
        app=create_app(Path(tmp)/'test.sqlite3',core_only=True,core_model_runner=board_plan,recap_model_runner=recap_fixture)
        uvicorn.run(app,host='127.0.0.1',port=8894,log_level='warning')
