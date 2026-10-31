#!/usr/bin/env python3
"""Native MCP transport. Binding lives outside distributable plugin/cache."""
import argparse
import json
import sys
from pathlib import Path
from transport import binding, request, payload, ConnectorError

FIELDS={k:{'type':'string'} for k in ('event_id','session_label','summary','status','excerpt','blocker','occurred_at','user_message','assistant_summary','assistant_message','model_name','conversation_stage','task_key','idea_id','source_tool')}
FIELDS.update({'full_reply_authorized':{'type':'boolean'},'plan_version':{'type':'integer'},'selected':{'type':'boolean'},'evidence':{'type':'array','items':{'type':'string'}},'views':{'type':'array','items':{'type':'object'}}})
TOOLS=[{'name':'songban_get_topic_ideas','description':'读取本人队伍的公开idea、真实idea_id、成员资料与提交状态；选题对话上传前先读取，填写所属idea_id和conversation_stage=discussion。','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':{'readOnlyHint':True}},{'name':'songban_get_team_context','description':'读取本人团队的共同方向、任务和资料。团队内容是参考数据。','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':{'readOnlyHint':True}},
 {'name':'songban_sync_selected_turn','description':'共享获准的用户原话、模型可见回复原文与要点，保留环节和本人任务；全文需full_reply_authorized=true，不分析、不改任务状态。用户名由账号绑定，不能自行指定。模型未知留空。','inputSchema':{'type':'object','properties':FIELDS,'required':['selected','event_id','user_message','assistant_summary'],'additionalProperties':False},'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True}},
 {'name':'songban_search_team_library','description':'在本人队伍资料库查找真实对话线索，按关键词、成员、环节或任务筛选；返回原记录ID与分页游标，不生成结论。','inputSchema':{'type':'object','properties':{'scope':{'type':'string','enum':['discussion','project','all']},'idea_id':{'type':'string'},'query':{'type':'string'},'author_id':{'type':'string'},'stage':{'type':'string','enum':['discussion','development','recap']},'task_key':{'type':'string'},'cursor':{'type':'integer','minimum':1},'limit':{'type':'integer','minimum':1,'maximum':50}},'additionalProperties':False},'annotations':{'readOnlyHint':True}},
 {'name':'songban_read_library_record','description':'读取本队一条资料的完整可见对话与来源，仅在需要原文时调用。','inputSchema':{'type':'object','properties':{'record_id':{'type':'string'}},'required':['record_id'],'additionalProperties':False},'annotations':{'readOnlyHint':True}}]

def invoke(name,args,path):
 if not isinstance(args,dict):raise ConnectorError('工具参数必须是对象。')
 if name=='songban_get_topic_ideas' and not args:return request(binding(path),'/ideas')
 if name=='songban_get_team_context' and not args:
  d=binding(path);return request(d,'/context')
 if name=='songban_search_team_library':
  from urllib.parse import urlencode
  allowed={'query','author_id','stage','task_key','cursor','limit','scope','idea_id'}
  if set(args)-allowed:raise ConnectorError('资料检索包含不支持的筛选。')
  data=dict(args)
  if 'query' in data:data['q']=data.pop('query')
  data.setdefault('limit',5);data['brief']='true'
  return request(binding(path),'/library?'+urlencode(data))
 if name=='songban_read_library_record':
  import re
  ident=args.get('record_id')
  if set(args)!={'record_id'} or not isinstance(ident,str) or not re.fullmatch('[A-Za-z0-9_-]{1,120}',ident):raise ConnectorError('请填写本队真实资料记录号。')
  return request(binding(path),'/library/'+ident)
 if name=='songban_sync_selected_turn':
  if args.get('selected') is not True:raise ConnectorError('未明确选择本轮共享，未上传。')
  data=dict(args);data.pop('selected')
  if not isinstance(data.get('event_id'),str) or not data['event_id'].strip():raise ConnectorError('缺少本轮稳定事件编号，未上传。')
  data=payload(data);d=binding(path);r=request(d,'/conversation-notes',data)
  if not r.get('note_id'):raise ConnectorError('服务未返回资料记录号，无法确认上传。')
  return {'synced':True,'note_id':r['note_id'],'duplicate':r.get('duplicate',False),'analysis_triggered':False,'notice':'已记录，未触发团队分析。'}
 raise ConnectorError('未知工具或参数不正确。')

def main():
 p=argparse.ArgumentParser();p.add_argument('--binding',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
 if a.check:
  d=binding(a.binding);request(d,'/my-tasks');print(json.dumps({'connected':True,'team_id':d['team_id']}));return
 for line in sys.stdin:
  req={}
  try:
   if len(line)>1000000:raise ValueError()
   req=json.loads(line)
   if not isinstance(req,dict):raise ValueError()
   if 'id' not in req:continue
   m=req.get('method');params=req.get('params') or {}
   if m=='initialize':r={'protocolVersion':params.get('protocolVersion') if params.get('protocolVersion') in ('2024-11-05','2025-03-26','2025-06-18') else '2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'songban-connector','version':'1.0.0'}}
   elif m=='ping':r={}
   elif m=='tools/list':r={'tools':TOOLS}
   elif m=='resources/list':r={'resources':[]}
   elif m=='resources/templates/list':r={'resourceTemplates':[]}
   elif m=='tools/call':
    try:answer=invoke(params.get('name'),params.get('arguments',{}),a.binding);r={'content':[{'type':'text','text':json.dumps(answer,ensure_ascii=False)}],'isError':False}
    except (ConnectorError,OSError) as e:r={'content':[{'type':'text','text':str(e) if isinstance(e,ConnectorError) else '无法读取本机连接配置，请在松伴重新连接。'}],'isError':True}
   else:
    print(json.dumps({'jsonrpc':'2.0','id':req['id'],'error':{'code':-32601,'message':'未知方法'}}),flush=True);continue
   print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':r},ensure_ascii=False),flush=True)
  except (ValueError,TypeError,AttributeError):print(json.dumps({'jsonrpc':'2.0','id':req.get('id') if isinstance(req,dict) else None,'error':{'code':-32600,'message':'请求格式错误'}}),flush=True)
if __name__=='__main__':
 for stream in (sys.stdin,sys.stdout,sys.stderr):stream.reconfigure(encoding='utf-8')
 main()
