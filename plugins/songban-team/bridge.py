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
import uuid
import urllib.error
import urllib.parse
import urllib.request

VERSION='1.0'
MAX_BYTES=280000


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
    if not ignore.exists():ignore.write_text('*\n',encoding='utf-8')
    return p


def config():
    p=Path(os.environ.get('SONGBAN_CONFIG',str(Path.cwd()/'.songban'/'connection.json')))
    data=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {}
    for key,env in [('url','SONGBAN_URL'),('team_id','SONGBAN_TEAM_ID'),('token','SONGBAN_TOKEN'),('base_path','SONGBAN_BASE_PATH'),('demo_session','SONGBAN_DEMO_SESSION')]:
        if os.environ.get(env):data[key]=os.environ[env]
    if not all(isinstance(data.get(k),str) and data[k] for k in ('url','team_id','token')):
        raise BridgeError('尚未连接。请先在当前项目运行 python3 bridge.py connect，或配置三个环境变量。')
    u=urllib.parse.urlsplit(data['url'])
    if not ((u.scheme=='https' or (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost','::1'))) and u.hostname and not (u.username or u.password or u.query or u.fragment) and u.path in ('','/')):
        raise BridgeError('团队服务需使用HTTPS，或本机HTTP地址；不要填写带密钥或额外路径的地址。')
    if data.get('base_path','') not in ('','/demo'):raise BridgeError('演示连接路径无效。')
    if 'demo_session' in data:
        try:uuid.UUID(data['demo_session'])
        except (ValueError,TypeError,AttributeError):raise BridgeError('演示会话无效，请重新连接。') from None
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',data['team_id']):raise BridgeError('队伍ID格式不正确。')
    if not data['token'].startswith('sbconn_'):raise BridgeError('请使用网页生成的插件连接凭证，不要使用账号密码或模型密钥。')
    if data.get('project_root') and Path(data['project_root']).resolve()!=Path.cwd().resolve():
        raise BridgeError('连接属于另一个项目目录，请进入原项目或在当前项目重新连接。')
    data['url']=data['url'].rstrip('/')
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def call(path,body=None):
    c=config();url=c['url']+c.get('base_path','')+'/api/core/teams/'+c['team_id']+path
    req=urllib.request.Request(url,data=encode(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+c['token'],'Content-Type':'application/json',**({'X-Songban-Demo':c['demo_session']} if c.get('demo_session') else {})},method='POST' if body is not None else 'GET')
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
    allowed={'event_id','tool','session_label','summary','status','evidence','blocker','views','excerpt','occurred_at','task_key','plan_version','origin','user_message','assistant_summary','assistant_message','model_name','conversation_stage','full_reply_authorized','idea_id','source_tool'}
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
    return prepare(json.loads(p.read_text(encoding='utf-8-sig')))


def enqueue(body):
    c=config();root=private_dir()/'outbox';root.mkdir(mode=0o700,exist_ok=True)
    digest=hashlib.sha256((c['url']+c['team_id']+c['token']).encode()).hexdigest()
    data={'connection':digest,'payload':body}
    name=hashlib.sha256((digest+body['event_id']).encode()).hexdigest()+'.json';p=root/name
    if p.exists() and p.read_text(encoding='utf-8-sig')!=encode(data):raise BridgeError('同一事件ID的队列内容不同，请创建新事件ID。')
    p.write_text(encode(data),encoding='utf-8');p.chmod(0o600)
    return p


def flush():
    c=config();digest=hashlib.sha256((c['url']+c['team_id']+c['token']).encode()).hexdigest();results=[];rejected=[]
    root=private_dir()/'outbox'
    for p in sorted(root.glob('*.json'),key=lambda p:p.stat().st_mtime) if root.exists() else []:
        stored=json.loads(p.read_text(encoding='utf-8-sig'))
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
    original=json.loads(Path(filename).read_text(encoding='utf-8-sig'))
    if not original.get('event_id'):
        data['event_id']='file-'+hashlib.sha256(encode({k:v for k,v in data.items() if k!='event_id'}).encode()).hexdigest()[:32]
    enqueue(data)
    return flush()


def pull_local_tasks():
    """Return direction + own tasks to file-based agents, not just MCP clients."""
    data=call('/my-tasks')
    root=private_dir();target=root/'team-state.json';content=encode(data)
    if not target.exists() or target.read_text(encoding='utf-8-sig')!=content:
        temporary=root/'team-state.tmp';temporary.write_text(content,encoding='utf-8');temporary.chmod(0o600);temporary.replace(target)
    return data


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
 {'name':'songban_sync_progress','description':'将用户授权的当前项目重要进展、必要对话摘录和证据同步到团队。不能上传其他项目或把团队建议回传成个人新事实。','inputSchema':REPORT_SCHEMA}
]


CONVERSATION_SCHEMA={'type':'object','properties':{
 'source_tool':{'type':'string'},'idea_id':{'type':'string'},'selected':{'type':'boolean'},'full_reply_authorized':{'type':'boolean'},'event_id':{'type':'string'},
 'user_message':{'type':'string'},'assistant_message':{'type':'string'},'assistant_summary':{'type':'string'},'model_name':{'type':'string'},
 'conversation_stage':{'type':'string','enum':['discussion','development','recap']},'task_key':{'type':'string'},'plan_version':{'type':'integer'}
},'required':['selected','event_id','user_message','assistant_summary'],'additionalProperties':False}
TOOLS.extend([{'name':'songban_get_topic_ideas','description':'读取本队公开idea及idea_id；选题可行性对话上传时填写idea_id和conversation_stage=discussion。','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':{'readOnlyHint':True}},
 {'name':'songban_sync_selected_turn','description':'将明确授权的本轮用户原话和AI可见回复归档到团队资料库。完整回复须full_reply_authorized=true；不修改任务状态。','inputSchema':CONVERSATION_SCHEMA},
 {'name':'songban_search_team_library','description':'从本队真实资料库检索线索，返回记录号和分页游标。只检索，不运行模型。','inputSchema':{'type':'object','properties':{'scope':{'type':'string','enum':['discussion','project','all']},'idea_id':{'type':'string'},'query':{'type':'string'},'author_id':{'type':'string'},'stage':{'type':'string'},'task_key':{'type':'string'},'cursor':{'type':'integer'},'limit':{'type':'integer','minimum':1,'maximum':50}},'additionalProperties':False},'annotations':{'readOnlyHint':True}},
 {'name':'songban_read_library_record','description':'按资料记录号读取本队完整对话原文。','inputSchema':{'type':'object','properties':{'record_id':{'type':'string'}},'required':['record_id'],'additionalProperties':False},'annotations':{'readOnlyHint':True}}
])


def library_tool(name,args):
    if name=='songban_get_topic_ideas':
        if args:raise BridgeError('读取idea不需要额外参数。')
        return call('/ideas')
    if name=='songban_sync_selected_turn':
        if args.get('selected') is not True:raise BridgeError('本轮没有明确授权共享。')
        body=dict(args);body.pop('selected')
        # A caller must supply a stable ID before a possibly interrupted write.
        if not isinstance(body.get('event_id'),str) or not body['event_id'].strip():raise BridgeError('缺少本轮稳定记录号。')
        data=prepare(body);data['selected']=True
        r=call('/conversation-notes',data)
        if not r.get('note_id'):raise BridgeError('未返回记录号，不能确认上传成功。')
        return r
    if name=='songban_search_team_library':
        if set(args)-{'query','author_id','stage','task_key','cursor','limit','scope','idea_id'}:raise BridgeError('检索参数不正确。')
        data=dict(args)
        if 'query' in data:data['q']=data.pop('query')
        data.setdefault('limit',5);data['brief']='true'
        return call('/library?'+urllib.parse.urlencode(data))
    ident=args.get('record_id')
    if set(args)!={'record_id'} or not isinstance(ident,str) or not re.fullmatch('[A-Za-z0-9_-]{1,120}',ident):raise BridgeError('请提供本队真实资料记录号。')
    return call('/library/'+ident)


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
                    elif name in ('songban_get_topic_ideas','songban_sync_selected_turn','songban_search_team_library','songban_read_library_record'):answer=library_tool(name,args)
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
        file=private_dir()/'connection.json';file.write_text(encode(data),encoding='utf-8');file.chmod(0o600)
        try:result=call('/context')
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
                        if not json.loads(f.read_text(encoding='utf-8-sig')).get('event_id'):data['event_id']='file-'+hashlib.sha256(encode({k:v for k,v in data.items() if k!='event_id'}).encode()).hexdigest()[:32]
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
    for stream in (sys.stdin,sys.stdout,sys.stderr):stream.reconfigure(encoding='utf-8')
    try:main()
    except KeyboardInterrupt:pass
    except Exception as e:
        print(redact(str(e)) if isinstance(e,BridgeError) else '配置或共享文件不正确，请按README检查。',file=sys.stderr);sys.exit(1)
