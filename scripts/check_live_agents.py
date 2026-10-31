"""Explicit paid model smoke test using synthetic data in a temporary database only."""
import os,sys,json,sqlite3,tempfile,uuid,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser();parser.add_argument('--env-file');parser.add_argument('--only',nargs='*');parser.add_argument('--output',default='../live-agent-results.json');args=parser.parse_args()
if args.env_file:
 for line in Path(args.env_file).read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   key,value=line.split('=',1)
   if key.strip() in {'TEAM_MODEL_API_KEY','TEAM_MODEL_BASE_URL','TEAM_MODEL_NAME','MODEL_API_KEY','MODEL_BASE_URL','MODEL_NAME','MODEL_ALLOWED_HOSTS','DEEPSEEK_API_KEY'}:os.environ[key.strip()]=value.strip().strip('\"\'')
from fastapi.testclient import TestClient
from app.main import create_app,digest,now
from app.recap_reports import run_model,validate_output
from app.workbench_model import request_workbench_model
results={'synthetic_data_only':True,'fixtures':False,'checks':{}};started=time.monotonic()
def save(key,result):
 results['checks'][key]=result;Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2));print(key,json.dumps(result,ensure_ascii=False),flush=True)
def probe(key,fn):
 if args.only and key not in args.only:return
 t=time.monotonic()
 try:result=fn();save(key,{'passed':True,'seconds':round(time.monotonic()-t,1),**(result or {})})
 except Exception as e:save(key,{'passed':False,'seconds':round(time.monotonic()-t,1),'error':getattr(e,'code',type(e).__name__),'message':getattr(e,'message',str(e)[:250])})
with tempfile.TemporaryDirectory(prefix='songban-live-validation-') as temp:
 path=Path(temp)/'test.sqlite3';app=create_app(path,core_only=True,enforce_journey=True);client=TestClient(app);user='a'
 with sqlite3.connect(path) as db:
  for key in ['a','b','probe']:db.execute('INSERT INTO people(id,phone,name,skills,token_hash,created_at) VALUES(?,?,?,?,?,?)',(key,'synthetic-'+key,'模拟成员'+key,'界面设计' if key=='a' else '网页开发',digest('test-'+key),now()))
 def call(path,body=None,method=None):
  r=client.request(method or ('POST' if body is not None else 'GET'),path,json=body,headers={'Authorization':'Bearer test-'+user});d=r.json()
  assert r.status_code==200,{'status':r.status_code,'error':d.get('error')};return d
 def interview_probe():
  global user
  user='probe';iv=call('/api/core/interview/start',{});assert iv['current_question']['text']
  iv=call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':'想做作业时间安排工具。我会画界面草图，不会独立写代码。可以投入6小时，希望和会开发的队友合作。'})
  if iv['status']=='asking':iv=call('/api/core/interview/finish',{'version':iv['version'],'request_id':uuid.uuid4().hex})
  assert iv['status']=='pending_confirmation';return {'question_and_evidence_profile':True}
 probe('interview',interview_probe)
 for user in ['a','b']:
  iv=call('/api/core/interview/manual-start',{})
  for answer in ['作业时间安排工具','会画草图，开发需要帮助' if user=='a' else '会写基础网页','6小时']:
   iv=call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':answer})
  call('/api/core/interview/confirm',{'version':iv['version'],'request_id':uuid.uuid4().hex})
 user='a'
 source='比赛：虚构周末创造赛；时间：2026年11月1日至2日；地点：线上；评分：用户价值40%、完成度40%、协作20%；材料：代码链接、网页和展示说明；截止：2026年11月2日18点（北京时间）。'
 def extract_probe():
  d=call('/api/journey/extract',{'text':source});assert all(d['fields'].get(k) for k in ['name','event_time','location','rubric','requirements','deadline']);return {'fields':len(d['fields']),'source_quotes_validated':True}
 probe('announcement',extract_probe)
 call('/api/journey/contest',{'name':'虚构周末创造赛','event_time':'两天','location':'线上','rubric':'用户价值40%、完成度40%、协作20%','requirements':'代码链接、网页和展示说明','deadline':'2026-11-02T18:00:00+08:00','source_text':source})
 team=call('/api/core/teams',{'name':'模拟模型验收队'});base='/api/core/teams/'+team['id']
 user='b';call('/api/core/join',{'code':team['code']})
 for user in ['a','b']:
  call(base+'/profile',{'strengths':'界面草图' if user=='a' else '基础网页','hours':6,'willingness':'设计和展示' if user=='a' else '交互实现'},'PUT')
  idea=call(base+'/ideas',{'title':'作业时间小助手' if user=='a' else '校园新闻聚合','problem':'任务安排不清楚' if user=='a' else '信息不集中','proposal':'单页输入任务、排序、完成打勾' if user=='a' else '爬取学校官网资讯并聚合'})
  if user=='a':idea_id=idea['id']
  call(base+'/ideas/ready',{'confirmed':True})
 user='a'
 def ranking_probe():
  board=call(base+'/ideas');d=call(base+'/ideas/rank',{'request_id':uuid.uuid4().hex,'expected_fingerprint':board['fingerprint']});assert d['status']=='ready',d.get('error');return {'all_ideas_ranked_and_citations_validated':True}
 probe('ranking',ranking_probe)
 call(base+'/topic/confirm',{'idea_id':idea_id,'confirmed':True});snap=call(base);call(base+'/direction',{**snap['direction'],'expected_revision':snap['revision']},'PUT')
 for user in ['a','b']:
  d=call(base+'/division')
  for answer in [('界面草图和展示' if user=='a' else '实现交互页面'),('能画清楚流程，不会编程' if user=='a' else '可独立做基础网页，复杂功能不做'),'6','提供可检查成果，先完成最小闭环，再请另一位队友逐项试用']:
   d=call(base+'/division/answers',{'round_id':d['round_id'],'step':d['me']['step'],'answer':answer})
  if user=='a':call(base+'/division/confirm',{'round_id':d['round_id'],'confirmed':True})
 def division_probe():
  d=call(base+'/division');d=call(base+'/division/confirm',{'round_id':d['round_id'],'confirmed':True});assert d['status']=='published',d.get('error');snap=call(base);assert {t['owner_id'] for t in snap['active_plan']['tasks']}=={'a','b'};return {'tasks':len(snap['active_plan']['tasks']),'both_members_assigned':True}
 probe('division',division_probe)
 def recap_probe():
  sources=[{'id':'reflection','kind':'reflection','content':{'feelings':'这次先画流程再开发更省时间，遇到问题会请队友试用。','ideas':'下次先找同学验证需求','result':'虚构比赛完成展示，尚无排名'}},{'id':'work1','kind':'work_record','content':'模拟成员画了输入、安排、完成三个页面步骤，经队友检查；开发由队友和AI协助。'}]
  out,model=run_model({'sources':sources});valid=validate_output(out,sources);return {'model':model,'observations':len(valid['observations']),'source_ids_validated':True}
 probe('parent_report',recap_probe)
 def workbench_probe():
  result=request_workbench_model({'role':{'id':'next_step','name':'排下一步'},'text':'根据这个方向给我一个可以立刻开始的小步骤','sources':[{'id':'direction','text':'两人各6小时，制作作业时间安排网页，只做输入、排序和勾选。'}]});assert result,'empty workbench response';return {'nonempty_validated_response':True}
 probe('workbench',workbench_probe)
 def materials_probe():
  space=call('/api/materials/space');url='/api/materials/spaces/'+space['id']
  src=call(url+'/sources',{'request_id':uuid.uuid4().hex,'kind':'text','name':'虚构验收公告','content':source,'nature':'sample'})['source']
  snap=call(url);call(url+'/sources/'+src['id']+'/parse',{'expected_revision':snap['revision']});snap=call(url)
  batch=call(url+'/generate',{'request_id':uuid.uuid4().hex,'expected_revision':snap['revision']});assert batch['status']=='completed',batch.get('error');items=batch['output']['items'];assert items,'empty materials result';assert any(i['kind']=='statement' and i['citations'] for i in items),'no quoted statements';return {'quoted_items_validated':True,'items':len(items)}
 probe('materials',materials_probe)
 client.close()
results['seconds']=round(time.monotonic()-started,1);Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2))

if any(not check['passed'] for check in results['checks'].values()):
 sys.exit(1)
