#!/usr/bin/env python3
"""Portable MCP stdio + CLI bridge. Python 3 standard library only.
No access to private agent history. Reads only the explicitly shared update file.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION='1.0'
MAX_BYTES=60000


def encode(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False)


def redact(s):
    s=re.sub(r'(?i)\bBearer\s+[^\s"\']+','Bearer [已隐藏]',s)
    s=re.sub(r'\b(?:sk-|sbconn_)[A-Za-z0-9_\-]{8,}','[密钥已隐藏]',s)
    return re.sub(r'(?i)((?:api[_ -]?key|access[_ -]?token|password|secret|密钥|密码)\s*[:=：]\s*)[^\s,，;；]+',r'\1[已隐藏]',s)


class BridgeError(Exception):
    def __init__(self,message,status=None):
        super().__init__(message)
        self.status=status


def private_dir():
    p=Path.cwd()/'.songban';p.mkdir(mode=0o700,exist_ok=True)
    ignore=p/'.gitignore'
    if not ignore.exists():ignore.write_text('*\n')
    return p


def config():
    p=Path(os.environ.get('SONGBAN_CONFIG',str(Path.cwd()/'.songban'/'connection.json')))
    data=json.loads(p.read_text()) if p.exists() else {}
    for key,env in [('url','SONGBAN_URL'),('team_id','SONGBAN_TEAM_ID'),('token','SONGBAN_TOKEN')]:
        if os.environ.get(env):data[key]=os.environ[env]
    if not all(isinstance(data.get(k),str) and data[k] for k in ('url','team_id','token')):
        raise BridgeError('尚未连接。请先在当前项目运行 python3 bridge.py connect，或配置三个环境变量。')
    u=urllib.parse.urlsplit(data['url'])
    if not ((u.scheme=='https' or (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost','::1'))) and u.hostname and not (u.username or u.password or u.query or u.fragment) and u.path in ('','/')):
        raise BridgeError('团队服务需使用HTTPS，或本机HTTP地址；不要填写带密钥或额外路径的地址。')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',data['team_id']):raise BridgeError('队伍ID格式不正确。')
    if not data['token'].startswith('sbconn_'):raise BridgeError('请使用网页生成的插件连接凭证，不要使用账号密码或模型密钥。')
    if data.get('project_root') and Path(data['project_root']).resolve()!=Path.cwd().resolve():
        raise BridgeError('连接属于另一个项目目录，请进入原项目或在当前项目重新连接。')
    data['url']=data['url'].rstrip('/')
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def call(path,body=None,method=None):
    c=config();url=c['url']+'/api/core/teams/'+c['team_id']+path
    req=urllib.request.Request(url,data=encode(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+c['token'],'Content-Type':'application/json'},method=method or ('POST' if body is not None else 'GET'))
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(req,timeout=20) as response:
            raw=response.read(1500000)
            if len(raw)>=1500000:raise BridgeError('团队返回内容过长。')
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        try:message=json.loads(e.read(5000))['error']['message']
        except Exception:message='团队服务拒绝请求。'
        raise BridgeError(f'HTTP {e.code}：'+redact(str(message)),status=e.code) from None
    except (urllib.error.URLError,TimeoutError,OSError):raise BridgeError('连接团队服务失败，检查网络和地址；未发送成功的文件仍在本机队列。') from None


def prepare(body):
    if not isinstance(body,dict):raise BridgeError('进展文件必须是JSON对象。')
    allowed={'event_id','tool','session_label','summary','status','evidence','blocker','views','excerpt','occurred_at','task_key','plan_version','origin'}
    if set(body)-allowed:raise BridgeError('进展含不支持的字段，请按示例填写。')
    # Round trip redacts only string values; never interpolates JSON as code.
    def walk(v):
        if isinstance(v,str):return redact(v)
        if isinstance(v,list):return [walk(x) for x in v]
        if isinstance(v,dict):return {k:walk(x) for k,x in v.items()}
        return v
    result=walk(body)
    result.setdefault('event_id','file-'+secrets.token_hex(12))
    result.setdefault('tool','个人智能体')
    if len(encode(result).encode())>MAX_BYTES:raise BridgeError('本次进展过大，请仅保留重要摘要和必要摘录。')
    return result


def read_update(filename):
    p=Path(filename).resolve()
    if not p.is_relative_to(Path.cwd().resolve()):raise BridgeError('只读取当前项目目录中的共享进展文件。')
    if p.stat().st_size>MAX_BYTES:raise BridgeError('进展文件过大。')
    return prepare(json.loads(p.read_text()))


def enqueue(body):
    c=config();root=private_dir()/'outbox';root.mkdir(mode=0o700,exist_ok=True)
    digest=hashlib.sha256((c['url']+c['team_id']+c['token']).encode()).hexdigest()
    data={'connection':digest,'payload':body}
    name=hashlib.sha256((digest+body['event_id']).encode()).hexdigest()+'.json';p=root/name
    if p.exists() and p.read_text()!=encode(data):raise BridgeError('同一事件ID的队列内容不同，请创建新事件ID。')
    p.write_text(encode(data));p.chmod(0o600)
    return p


def flush():
    c=config();digest=hashlib.sha256((c['url']+c['team_id']+c['token']).encode()).hexdigest();results=[];rejected=[]
    root=private_dir()/'outbox'
    for p in sorted(root.glob('*.json'),key=lambda p:p.stat().st_mtime) if root.exists() else []:
        stored=json.loads(p.read_text())
        if stored['connection']!=digest:continue  # never upload an old team's queue to a new team
        try:
            result=call('/reports',stored['payload']);p.unlink();results.append(result)
        except BridgeError as e:
            if e.status not in (400,403,404,409,413,422):raise
            failed=private_dir()/'rejected';failed.mkdir(mode=0o700,exist_ok=True)
            p.replace(failed/p.name)
            rejected.append({'event_id':stored['payload']['event_id'],'message':str(e),'action':'记录已移到本机rejected目录，请更正后使用新事件ID；没有挡住其他新进展。'})
    return {'sent':len(results),'results':results,'rejected':rejected}


def sync_file(filename):
    data=read_update(filename)
    # Content-derived ID when absent in input gives hooks/retries deterministic deduplication.
    original=json.loads(Path(filename).read_text())
    if not original.get('event_id'):
        data['event_id']='file-'+hashlib.sha256(encode({k:v for k,v in data.items() if k!='event_id'}).encode()).hexdigest()[:32]
    enqueue(data)
    return flush()


def pull_local_tasks():
    """Return direction + own tasks to file-based agents, not just MCP clients."""
    data=call('/my-tasks')
    root=private_dir();target=root/'team-state.json';content=encode(data)
    if not target.exists() or target.read_text()!=content:
        temporary=root/'team-state.tmp';temporary.write_text(content);temporary.chmod(0o600);temporary.replace(target)
    return data


def get_phase():
    return call('/phase')


def answer_phase(phase_id, question_id, answer):
    return call('/phase/'+urllib.parse.quote(phase_id,safe='')+'/answer', {'question_id':question_id,'answer':answer})


def confirm_phase_pause(phase_id):
    return call('/phase/'+urllib.parse.quote(phase_id,safe='')+'/pause', {'confirm':True})

def submit_phase_idea(phase_id, idea):
    return call('/phase/'+urllib.parse.quote(phase_id,safe='')+'/ideas', idea)

def confirm_phase_idea_upload(phase_id):
    return call('/phase/'+urllib.parse.quote(phase_id,safe='')+'/ideas/confirm-upload', {'confirm':True})

def vote_phase_idea(phase_id, idea_id):
    return call('/phase/'+urllib.parse.quote(phase_id,safe='')+'/ideas/'+urllib.parse.quote(idea_id,safe='')+'/vote', {})

def confirm_phase_conversation(phase_id):
    return call('/phase/'+urllib.parse.quote(phase_id,safe='')+'/conversation-confirm', {'confirm':True})


def check_task_step(task_key, step_index, checked, plan_version, revision, note=''):
    return call('/tasks/'+urllib.parse.quote(task_key,safe='')+'/steps/'+str(int(step_index)), {'expected_revision':revision,'plan_version':plan_version,'checked':bool(checked),'note':note})


REPORT_SCHEMA={'type':'object','properties':{
 'event_id':{'type':'string','description':'本次进展唯一ID；重试时保持相同'},
 'tool':{'type':'string'},'session_label':{'type':'string'},'summary':{'type':'string'},
 'status':{'type':'string','enum':['discussion','in_progress','blocked','reported_done']},
 'evidence':{'type':'array','items':{'type':'string'}},'blocker':{'type':'string'},
 'views':{'type':'array','items':{'type':'object','properties':{'topic':{'type':'string'},'position':{'type':'string'}},'required':['topic','position'],'additionalProperties':False}},
 'excerpt':{'type':'string','description':'仅包含用户已同意向本队分享的必要对话摘录'},
 'occurred_at':{'type':'string'},'task_key':{'type':'string'},'plan_version':{'type':'integer'},'origin':{'type':'string','enum':['personal_agent','human']}
},'required':['event_id','tool','summary'],'additionalProperties':False}
TOOLS=[
 {'name':'songban_get_team_context','description':'读取本队已确认方向、评分要求、成员、进展来源和不同观点。只将团队确认安排作为执行依据；报告不是已经独立核实的事实。','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'songban_get_my_tasks','description':'读取本人当前已确认任务、检查方法和统一方向。在工作开始及方向可能变化时调用。','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'songban_get_phase','description':'读取本人当前阶段问题、暂停确认状态和阶段建议；阶段问题由团队模型按成员分工生成。','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'songban_submit_phase_answer','description':'提交本人对当前阶段问题的回答，只能提交自己的问题。','inputSchema':{'type':'object','properties':{'phase_id':{'type':'string'},'question_id':{'type':'string'},'answer':{'type':'string'}},'required':['phase_id','question_id','answer'],'additionalProperties':False}},
 {'name':'songban_confirm_phase_pause','description':'确认本人已暂停当前工作并参加阶段讨论。所有成员确认后，队长可生成阶段建议。','inputSchema':{'type':'object','properties':{'phase_id':{'type':'string'}},'required':['phase_id'],'additionalProperties':False}},
 {'name':'songban_submit_phase_idea','description':'通过个人AI整理并上传自己的候选黑客松方案；只上传用户明确授权的摘要。','inputSchema':{'type':'object','properties':{'phase_id':{'type':'string'},'title':{'type':'string'},'summary':{'type':'string'},'target_user':{'type':'string'},'core_chain':{'type':'string'},'technical_difficulty':{'type':'string'},'expected_deliverable':{'type':'string'},'source_ids':{'type':'array','items':{'type':'string'}}},'required':['phase_id','title','summary'],'additionalProperties':False}},
 {'name':'songban_confirm_phase_idea_upload','description':'确认本人已上传候选方案，供团队显示3/4、4/4确认状态。','inputSchema':{'type':'object','properties':{'phase_id':{'type':'string'}},'required':['phase_id'],'additionalProperties':False}},
 {'name':'songban_confirm_phase_conversation','description':'确认本人已通过松伴连接器上传了有效的个人AI对话；没有连接器记录时不会确认。','inputSchema':{'type':'object','properties':{'phase_id':{'type':'string'}},'required':['phase_id'],'additionalProperties':False}},
 {'name':'songban_vote_phase_idea','description':'在个人电脑投票支持一个候选方案；每轮每人只能保留一个投票。','inputSchema':{'type':'object','properties':{'phase_id':{'type':'string'},'idea_id':{'type':'string'}},'required':['phase_id','idea_id'],'additionalProperties':False}},
 {'name':'songban_check_my_task_step','description':'勾选或取消本人正式任务中的一个规划步骤，并同步团队面板。','inputSchema':{'type':'object','properties':{'task_key':{'type':'string'},'step_index':{'type':'integer','minimum':0},'checked':{'type':'boolean'},'plan_version':{'type':'integer'},'revision':{'type':'integer'},'note':{'type':'string'}},'required':['task_key','step_index','checked','plan_version','revision'],'additionalProperties':False}},
 {'name':'songban_sync_progress','description':'将用户授权的当前项目重要进展、必要对话摘录和证据同步到团队。不能上传其他项目或把团队建议回传成个人新事实。','inputSchema':REPORT_SCHEMA}
]


def mcp():
    for line in sys.stdin:
        if len(line)>1000000:
            print(encode({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'请求过大'}}),flush=True);continue
        req={}
        try:
            req=json.loads(line);ident=req.get('id');method=req.get('method')
            if 'id' not in req:continue
            if method=='initialize':
                wanted=req.get('params',{}).get('protocolVersion')
                result={'protocolVersion':wanted if wanted in ('2024-11-05','2025-03-26','2025-06-18') else '2024-11-05','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'songban-team','version':VERSION},'instructions':'先读取共同方向和本人任务。仅共享本项目获准摘要及必要摘录。个人报告不等于验证完成；不能自动发布团队方向。'}
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':TOOLS}
            elif method=='tools/call':
                params=req.get('params',{});name=params.get('name');args=params.get('arguments',{})
                try:
                    if not isinstance(args,dict):raise BridgeError('工具参数必须是对象。')
                    if name=='songban_get_team_context' and not args:answer=call('/context')
                    elif name=='songban_get_my_tasks' and not args:answer=call('/my-tasks')
                    elif name=='songban_get_phase' and not args:answer=get_phase()
                    elif name=='songban_submit_phase_answer':answer=answer_phase(args.get('phase_id',''),args.get('question_id',''),args.get('answer',''))
                    elif name=='songban_confirm_phase_pause':answer=confirm_phase_pause(args.get('phase_id',''))
                    elif name=='songban_submit_phase_idea':answer=submit_phase_idea(args.get('phase_id',''),{k:args[k] for k in ('title','summary','target_user','core_chain','technical_difficulty','expected_deliverable','source_ids') if k in args})
                    elif name=='songban_confirm_phase_idea_upload':answer=confirm_phase_idea_upload(args.get('phase_id',''))
                    elif name=='songban_confirm_phase_conversation':answer=confirm_phase_conversation(args.get('phase_id',''))
                    elif name=='songban_vote_phase_idea':answer=vote_phase_idea(args.get('phase_id',''),args.get('idea_id',''))
                    elif name=='songban_check_my_task_step':answer=check_task_step(args.get('task_key',''),args.get('step_index',-1),args.get('checked'),args.get('plan_version'),args.get('revision'),args.get('note',''))
                    elif name=='songban_sync_progress':
                        data=prepare(args);enqueue(data);answer=flush()
                    else:raise BridgeError('未知工具或参数不正确。')
                    result={'content':[{'type':'text','text':encode(answer)}],'isError':bool(answer.get('rejected'))}
                except Exception as e:result={'content':[{'type':'text','text':redact(str(e)) if isinstance(e,BridgeError) else '插件读取或连接失败，请核对配置。'}],'isError':True}
            else:
                print(encode({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'未知方法'}}),flush=True);continue
            print(encode({'jsonrpc':'2.0','id':ident,'result':result}),flush=True)
        except Exception:
            print(encode({'jsonrpc':'2.0','id':req.get('id') if isinstance(req,dict) else None,'error':{'code':-32700,'message':'请求格式错误'}}),flush=True)


def main():
    # Installed MCP hosts may launch in a different working directory.
    # Pin file access to the project explicitly selected during installation.
    selected=os.environ.get('SONGBAN_PROJECT_ROOT')
    if selected:
        folder=Path(selected).expanduser().resolve()
        if not folder.is_dir():raise BridgeError('安装时选择的项目目录已不存在，请重新安装连接。')
        os.chdir(folder)
    p=argparse.ArgumentParser(description='松伴通用团队连接：MCP、命令行、共享文件自动同步')
    p.add_argument('mode',nargs='?',default='mcp',choices=['mcp','connect','context','tasks','sync','watch','flush','hook'])
    p.add_argument('--file',default='songban-update.json');p.add_argument('--interval',type=float,default=2)
    args=p.parse_args()
    if args.mode=='mcp':mcp();return
    if args.mode=='connect':
        data={'url':input('团队网站地址（如 http://127.0.0.1:8886）：').strip(),'team_id':input('队伍ID：').strip(),'token':getpass.getpass('插件连接凭证（输入不显示）：').strip(),'project_root':str(Path.cwd().resolve())}
        file=private_dir()/'connection.json';file.write_text(encode(data));file.chmod(0o600)
        try:result=call('/my-tasks')
        except Exception:file.unlink(missing_ok=True);raise
        print('连接成功；凭证保存在当前项目已忽略的 .songban 目录。可以运行 watch 自动同步共享文件。');return
    if args.mode=='watch':
        config();last='';last_pull=0;print('正在监听获准分享的进展文件，并每5秒取回共同方向与本人任务；Ctrl+C停止。不会读取其他对话。',flush=True)
        while True:
            try:
                f=Path(args.file)
                if f.exists():
                    stamp=hashlib.sha256(f.read_bytes()).hexdigest()
                    if stamp!=last:
                        data=read_update(args.file)
                        if not json.loads(f.read_text()).get('event_id'):data['event_id']='file-'+hashlib.sha256(encode({k:v for k,v in data.items() if k!='event_id'}).encode()).hexdigest()[:32]
                        enqueue(data);last=stamp
                result=flush()
                if result['sent'] or result['rejected']:print(encode(result),flush=True)
                if time.monotonic()-last_pull>=5:
                    pull_local_tasks();last_pull=time.monotonic()
            except (BridgeError,ValueError,OSError) as e:print(redact(str(e)) if isinstance(e,BridgeError) else '进展文件正在更新或格式不对，保留队列等待下一次。',file=sys.stderr,flush=True)
            time.sleep(max(1,args.interval))
    else:
        try:
            if args.mode=='context':result=call('/context')
            elif args.mode=='tasks':result=call('/my-tasks')
            elif args.mode=='flush':result=flush()
            else:result=sync_file(args.file)
            print('{}' if args.mode=='hook' else encode(result))
        except Exception:
            if args.mode=='hook':
                print('松伴本轮未同步，请查看网络和共享进展文件。',file=sys.stderr);print('{}');return
            raise


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception as e:
        print(redact(str(e)) if isinstance(e,BridgeError) else '配置或共享文件不正确，请按README检查。',file=sys.stderr);sys.exit(1)
