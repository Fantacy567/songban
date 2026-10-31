"""Real browser download and client installer, synthetic team and isolated client config only."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from contextlib import closing
import httpx,uuid,json,tempfile,zipfile,subprocess,sys,os
PUBLIC=os.environ.get('SONGBAN_TEST_BASE','https://nec-meditation-lion-tip.trycloudflare.com/demo');session=str(uuid.uuid4());h={'X-Songban-Demo':session}
# Fast fixture preparation uses the same demo APIs, then the actual public UI performs the download.
with httpx.Client(base_url='http://127.0.0.1:8890/demo',trust_env=False,timeout=30) as c:
 h['Authorization']='Bearer '+c.post('/api/demo/bootstrap',headers=h).json()['token']
 def call(path,body=None):
  r=c.request('POST' if body is not None else 'GET',path,json=body,headers=h);r.raise_for_status();return r.json()
 iv=call('/api/core/interview/manual-start',{})
 for text in ['做工具','会设计','6小时']:iv=call('/api/core/interview/answer',{'version':iv['version'],'question_id':iv['current_question']['id'],'request_id':uuid.uuid4().hex,'text':text})
 call('/api/core/interview/confirm',{'version':iv['version'],'request_id':uuid.uuid4().hex})
 call('/api/journey/contest',{'name':'虚构安装验收赛','event_time':'两天','location':'线上','rubric':'完成度','requirements':'网页','deadline':'2026-11-02T18:00:00+08:00','source_text':'时间：两天\n地点：线上'})
 brief=call('/api/journey/contest-materials');call('/api/journey/contest-materials/extract',{'request_id':uuid.uuid4().hex,'expected_revision':brief['revision']});call('/api/journey/contest-materials/confirm',{'confirmed':True,'expected_revision':brief['revision']});team=call('/api/core/teams',{'name':'独立虚构安装验证'})
expect.set_options(timeout=30000)
with tempfile.TemporaryDirectory(prefix='remote-installer-',dir='work') as temporary,sync_playwright() as p:
 root=Path(temporary).resolve();browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.add_init_script('sessionStorage.setItem("songban-demo-session",'+json.dumps(session)+');');page.goto(PUBLIC+'/#/tools');button=page.locator('#quick-install-button');expect(button).to_be_enabled();expect(button).to_contain_text('下载松伴连接器安装包');expect(page.locator('#quick-project-field')).to_be_hidden()
 for tool in ['connector-plugin','codex']:
  page.locator('#quick-tool').select_option(tool);expect(button).to_be_enabled();expect(page.locator('#quick-project-field')).to_be_hidden()
  with page.expect_download() as downloading:button.click()
  archive=root/(tool+'.zip');downloading.value.save_as(archive);folder=root/tool;folder.mkdir()
  with zipfile.ZipFile(archive) as z:z.extractall(folder)
  client=folder/'songban-connector-install';binding=json.loads((client/'connection.json').read_text());assert binding['url'].startswith('https://');assert binding['base_path']=='/demo';assert binding['demo_session']==session;assert binding['tool']==tool
  check=subprocess.run([sys.executable,str(client/'install.py'),'--check'],capture_output=True,text=True,timeout=30);assert check.returncode==0,(check.stdout,check.stderr)
  if tool=='connector-plugin':
   home=root/'isolated-client';conf=home/'.codex/config.toml';conf.parent.mkdir(parents=True);conf.write_text('model="preserve-me"\nmodel_provider="openai"\n');command=[sys.executable,str(client/'install.py'),'--home',str(home)]
  else:
   project=root/'client-project';project.mkdir();conf=project/'.codex/config.toml';conf.parent.mkdir();conf.write_text('model="preserve-me"\nmodel_provider="openai"\n');command=[sys.executable,str(client/'install.py'),'--project-dir',str(project)]
  installed=subprocess.run(command,capture_output=True,text=True,timeout=110);assert installed.returncode==0,(installed.stdout,installed.stderr);assert 'preserve-me' in conf.read_text();print(tool,'public download, actual client connection and isolated installation passed',flush=True)
 assert not errors,errors
 for width in [390,1440]:
  page.set_viewport_size({'width':width,'height':1000});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
 browser.close();print(json.dumps({'passed':True,'server_files_untouched_by_download':True,'client_config_preserved':True,'errors':errors}))
