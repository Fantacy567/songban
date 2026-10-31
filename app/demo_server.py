"""Same product, isolated database and labelled offline model fixtures, loopback by default; explicit public origin opt-in."""
import tempfile,uuid,secrets,sqlite3,json,threading,os
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit
import httpx
from starlette.responses import HTMLResponse,JSONResponse
from .main import create_app,ROOT,digest,now
from . import demo_scenario as fixture
BOOT='''<script>window.SONGBAN_DEMO=true;window.SONGBAN_DEMO_BASE=__DEMO_BASE__;const demoId=sessionStorage.getItem('songban-demo-session')||crypto.randomUUID();sessionStorage.setItem('songban-demo-session',demoId);const demoFetch=window.fetch.bind(window);window.fetch=(input,init={})=>{const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.origin===location.origin&&url.pathname.startsWith('/api/')){const h=new Headers(init.headers);h.set('X-Songban-Demo',demoId);return demoFetch(window.SONGBAN_DEMO_BASE+url.pathname+url.search,{...init,headers:h});}return demoFetch(input,init);};</script>'''
class Demo:
 def __init__(self,base_path=""):
  self.base_path=base_path
  self.tmp=tempfile.TemporaryDirectory(prefix='songban-unified-demo-');self.sessions={};self.lock=threading.Lock();self.shell=create_app(Path(self.tmp.name)/'shell.sqlite3',enforce_journey=True)
 def session(self,key):
  with self.lock:
   if key not in self.sessions:
    if len(self.sessions)>=100:raise ValueError('演示会话已满，请重启演示服务。')
    app=create_app(Path(self.tmp.name)/(key+'.sqlite3'),core_only=True,materials_model_runner=fixture.materials,workbench_model_runner=fixture.workbench,core_model_runner=fixture.plan,idea_model_runner=fixture.ranking,recap_model_runner=fixture.recap,interview_runner=fixture.interview,enforce_journey=True);app.state.demo=True;app.state.demo_base_path=self.base_path
    users=[]
    with closing(sqlite3.connect(app.state.db_path)) as con:
     for name in ['小松（演示）','小林（模拟队友）']:
      ident=uuid.uuid4().hex;token=secrets.token_urlsafe(32);users.append((ident,token))
      con.execute('INSERT INTO people(id,phone,name,skills,token_hash,created_at) VALUES(?,?,?,?,?,?)',(ident,'demo-'+ident,name,'界面设计' if len(users)==1 else '网页开发',digest(token),now()))
     con.commit()
    self.sessions[key]=(app,users)
   return self.sessions[key]
 async def __call__(self,scope,receive,send):
  if scope['type']!='http':return await self.shell(scope,receive,send)
  headers=dict(scope['headers']);host=urlsplit('//'+headers.get(b'host',b'').decode()).hostname;peer=(scope.get('client') or ('',0))[0]
  public_origin=os.environ.get('SONGBAN_DEMO_PUBLIC_ORIGIN','').rstrip('/')
  public=urlsplit(public_origin)
  public_allowed=public.scheme=='https' and bool(public.hostname) and headers.get(b'host',b'').decode()==public.netloc
  local_allowed=host in ['127.0.0.1','localhost','testserver'] and peer in ['127.0.0.1','::1','testclient']
  if not (local_allowed or public_allowed):return await JSONResponse({'error':{'message':'演示仅限本机访问。'}},403)(scope,receive,send)
  path=scope['path']
  if path=='/':return await HTMLResponse((ROOT/'static/songban.html').read_text().replace('<head>','<head>'+BOOT.replace('__DEMO_BASE__',json.dumps(self.base_path))),headers={'Cache-Control':'no-store'})(scope,receive,send)
  key=headers.get(b'x-songban-demo',b'').decode()
  if path.startswith('/api/'):
   try:uuid.UUID(key);app,users=self.session(key)
   except ValueError:return await JSONResponse({'error':{'message':'请重新打开演示页面。'}},409)(scope,receive,send)
   app.state.demo_base_url=(public_origin if public_allowed else 'http://'+headers.get(b'host',b'127.0.0.1:8886').decode())+self.base_path
   if path=='/api/demo/bootstrap':return await JSONResponse({'token':users[0][1],'demo':True})(scope,receive,send)
   if path=='/api/demo/peer':
    # Only this session's synthetic teammate. Advance via ordinary checked APIs.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
     async def call(path,body=None,method=None,who=1):
      r=await c.request(method or ('POST' if body is not None else 'GET'),path,json=body,headers={'Authorization':'Bearer '+users[who][1]});r.raise_for_status();return r.json()
     try:
      teams=(await call('/api/core/me',who=0))['teams']
      if not teams:return await JSONResponse({'message':'先创建队伍，再让模拟队友加入。'})(scope,receive,send)
      team=teams[0];base='/api/core/teams/'+team['id'];iv=await call('/api/core/interview')
      if iv['status']=='not_started':iv=await call('/api/core/interview/start',{})
      while iv['status']=='asking':iv=await call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':['做作业时间工具','会做简单网页','6小时'][min(iv['asked_count']-1,2)]})
      if iv['status']!='confirmed':await call('/api/core/interview/confirm',{'version':iv['version'],'request_id':uuid.uuid4().hex})
      await call('/api/core/join',{'code':team['code']})
      snap=await call(base);stage=(await call('/api/journey?team_id='+team['id']))['stage']
      if stage=='ideas':
       await call(base+'/profile',{'strengths':'网页开发','willingness':'实现交互','hours':6},'PUT')
       await call(base+'/profile',{'strengths':'界面设计','willingness':'草图和流程','hours':6},'PUT',0)
       board=await call(base+'/ideas')
       if not any(x['user_id']==users[1][0] for x in board['ideas']):await call(base+'/ideas',{'title':'校园活动提醒器','problem':'同学容易错过活动','proposal':'做简单的活动列表和提醒说明'})
       for who in [0,1]:
        await call(base+'/conversation-notes',{'event_id':'demo-idea-dialogue-'+str(who),'selected':True,'origin':'human','source_tool':'Codex（演示）','user_message':'（虚构示例）我是设计师，6小时能做一个作业安排工具吗？' if who==0 else '（虚构示例）我是开发同学，怎样缩小功能范围？','assistant_message':'（预置示例）先做输入任务、按时间安排、完成打勾三个步骤；设计和实现可以分开，最后请队友试用。','assistant_summary':'虚构可行性对话：缩小范围，分工后试用。','full_reply_authorized':True,'conversation_stage':'discussion'},who=who)
       await call(base+'/ideas/ready',{'confirmed':True})
      elif stage=='division':
       d=await call(base+'/division');answers=['实现演示页','能独立做基础网页，复杂逻辑请AI协助','6','提交可运行网页，队友逐步试用']
       while d['me']['step']<4:d=await call(base+'/division/answers',{'round_id':d['round_id'],'step':d['me']['step'],'answer':answers[d['me']['step']]})
       await call(base+'/division/confirm',{'round_id':d['round_id'],'confirmed':True})
      elif stage=='work':
       await call(base+'/conversation-notes',{'event_id':'demo-development-dialogue','selected':True,'origin':'human','source_tool':'Codex（演示）','user_message':'（虚构示例）队友试用时找不到返回按钮，如何改进？','assistant_message':'（预置示例）在安排页加上明确的返回入口，保留已输入内容，然后请队友再按三个步骤检查。','assistant_summary':'虚构开发发现：补上返回入口并保留输入。','full_reply_authorized':True,'conversation_stage':'development'},who=0)
       for task in snap['active_plan']['tasks']:
        if task['owner_id']==users[1][0] and task['status']!='reported_done' and not task['waiting_on']:
         await call(base+'/reports',{'event_id':uuid.uuid4().hex,'tool':'模拟队友','origin':'human','summary':'虚构演示：可运行页面已完成','evidence':['演示中已检查三个页面步骤'],'task_key':task['key'],'plan_version':snap['plan_version'],'status':'reported_done'})
       snap=await call(base)
       for task in snap['active_plan']['tasks']:
        if task['owner_id']==users[0][0] and task['handoff_state']=='waiting_review' and not task['waiting_on']:
         await call(base+'/tasks/'+task['key']+'/check',{'expected_revision':snap['revision'],'plan_version':snap['plan_version'],'report_id':task['latest_report_id'],'verdict':'accepted','note':'模拟同伴检查：三个步骤都有清楚说明。'});snap=await call(base)
      return await JSONResponse({'done':True,'stage':stage})(scope,receive,send)
     except httpx.HTTPStatusError as e:return await JSONResponse(e.response.json(),status_code=e.response.status_code)(scope,receive,send)
   return await app(scope,receive,send)
  if path.startswith('/family/reports/'):
   token=path.split('/')[3]
   for app,_ in self.sessions.values():
    with closing(sqlite3.connect(app.state.db_path)) as con:
     found=con.execute('SELECT 1 FROM recap_shares WHERE token=?',(token,)).fetchone()
    if found:return await app(scope,receive,send)
  return await self.shell(scope,receive,send)
app=Demo()
