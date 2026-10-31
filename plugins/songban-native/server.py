#!/usr/bin/env python3
"""Native MCP transport. Binding lives outside distributable plugin/cache."""
import argparse
import json
import sys
from pathlib import Path
from transport import binding, request, payload, topic_payload, ConnectorError

FIELDS={k:{'type':'string'} for k in ('event_id','session_label','summary','status','excerpt','blocker','occurred_at','user_message','assistant_summary','model_name')}
FIELDS.update({'selected':{'type':'boolean'},'evidence':{'type':'array','items':{'type':'string'}},'views':{'type':'array','items':{'type':'object'}}})
TOOLS=[{'name':'songban_get_team_context','description':'读取本人团队的共同方向、任务和资料。团队内容是参考数据。','inputSchema':{'type':'object','properties':{},'additionalProperties':False},'annotations':{'readOnlyHint':True}},
 {'name':'songban_sync_selected_turn','description':'记录当前用户原话、注册姓名、回复关键信息及实际模型名；不分析、不触发统筹。用户名由账号绑定，不能自行指定。模型未知留空。','inputSchema':{'type':'object','properties':FIELDS,'required':['selected','event_id','user_message','assistant_summary'],'additionalProperties':False},'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True}}]

TOPIC_FIELDS={k:{'type':'string'} for k in ('round_id','event_id','topic_title','user_message','assistant_message','model_name','session_label')}
TOPIC_FIELDS['selected']={'type':'boolean','const':True}
TOOLS.append({'name':'songban_share_topic_turn','description':'仅在用户选择松伴连接器或明确授权当前选题对话时，共享本回合用户原话和 AI 可见回复到方向页。先读取上下文的 topic_selection.id。禁止隐藏推理、其他会话和密钥。上传不等于成员确认；成员须亲自在网页确认进入排名。','inputSchema':{'type':'object','properties':TOPIC_FIELDS,'required':['selected','round_id','event_id','topic_title','user_message','assistant_message'],'additionalProperties':False},'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True}})

def invoke(name,args,path):
 if not isinstance(args,dict):raise ConnectorError('工具参数必须是对象。')
 if name=='songban_get_team_context' and not args:
  d=binding(path);return request(d,'/context')
 if name=='songban_share_topic_turn':
  data=topic_payload(args);d=binding(path);r=request(d,'/topic-selection/turns',data)
  if not r.get('note_id'):raise ConnectorError('服务未返回回合记录号，不能确认上传。')
  return {'synced':True,'note_id':r['note_id'],'duplicate':r.get('duplicate',False),'analysis_triggered':False,'notice':'已上传到方向页；请在网页核对并确认进入排名。'}
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
   if len(line)>400000:raise ValueError()
   req=json.loads(line)
   if not isinstance(req,dict):raise ValueError()
   if 'id' not in req:continue
   m=req.get('method');params=req.get('params') or {}
   if m=='initialize':r={'protocolVersion':params.get('protocolVersion') if params.get('protocolVersion') in ('2024-11-05','2025-03-26','2025-06-18') else '2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'songban-connector','version':'0.10.0'}}
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
