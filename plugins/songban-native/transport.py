#!/usr/bin/env python3
"""Explicit selected-turn skill transport. No chat-log scanning or background hooks."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import uuid


class ConnectorError(Exception):pass


def redact(s):
 s=re.sub(r'(?i)\bBearer\s+[^\s"\']+','Bearer [已隐藏]',s)
 s=re.sub(r'\b(?:sk-|sbconn_)[A-Za-z0-9_\-]{8,}','[密钥已隐藏]',s)
 return re.sub(r'(?i)((?:api[_ -]?key|access[_ -]?token|password|secret|密钥|密码)\s*[:=：]\s*)[^\s,，;；]+',r'\1[已隐藏]',s)


def binding(path=None):
 p=Path(path) if path else Path(__file__).resolve().parent.parent/'binding.json'
 try:
  d=json.loads(p.read_text())
  if 'connection_file' in d:d=json.loads(Path(d['connection_file']).expanduser().read_text())
 except (ValueError,OSError,TypeError):raise ConnectorError('松伴连接器尚未绑定团队，请在松伴网页安装或重新绑定。') from None
 if not isinstance(d,dict) or not all(isinstance(d.get(k),str) and d[k] for k in ('url','team_id','token')):raise ConnectorError('团队连接配置不完整。')
 u=urlsplit(d['url'])
 if not ((u.scheme=='https' or (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost','::1'))) and u.hostname and not (u.username or u.password or u.query or u.fragment) and u.path in ('','/')):raise ConnectorError('团队地址无效；只支持HTTPS或明确的本机地址。')
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',d['team_id']) or not d['token'].startswith('sbconn_'):raise ConnectorError('请使用本人在松伴生成的团队连接。')
 return d


class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):return None


def request(d,suffix,data=None):
 raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if data is not None else None
 req=urllib.request.Request(d['url'].rstrip('/')+'/api/core/teams/'+d['team_id']+suffix,data=raw,headers={'Authorization':'Bearer '+d['token'],'Content-Type':'application/json'},method='POST' if raw is not None else 'GET')
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
  with opener.open(req,timeout=20) as r:
   raw=r.read(1500000)
   if len(raw)>=1500000:raise ConnectorError('团队响应过长，未读取。')
   return json.loads(raw)
 except urllib.error.HTTPError as e:
  try:msg=json.loads(e.read(5000))['error']['message']
  except Exception:msg='团队服务拒绝请求。'
  raise ConnectorError('未同步：'+redact(str(msg))) from None
 except (ValueError,UnicodeDecodeError,TypeError):raise ConnectorError('团队响应格式异常，不能确认同步成功。') from None
 except (urllib.error.URLError,TimeoutError,OSError) as e:
  reason=getattr(e,'reason',e)
  if isinstance(reason,PermissionError):msg='本轮未同步：执行环境阻止访问本机松伴。请使用已安装的原生插件工具，不要绕过权限运行上传脚本。'
  elif isinstance(reason,ConnectionRefusedError):msg='本轮未同步：松伴服务未启动或连接地址不正确，请打开松伴后重试。'
  elif isinstance(reason,TimeoutError):msg='本轮未同步：连接松伴超时，请检查服务与网络。'
  else:msg='本轮未同步：无法连接松伴，请检查服务、地址和本机网络权限。'
  raise ConnectorError(msg) from None


def payload(data):
 if not isinstance(data,dict):raise ConnectorError('本轮摘要必须是JSON对象。')
 allowed={'event_id','session_label','summary','status','views','evidence','excerpt','blocker','occurred_at','user_message','assistant_summary','model_name'}
 if set(data)-allowed:raise ConnectorError('本轮摘要含不支持字段；不能自行指定成员或其他队伍。')
 def clean(v):
  if isinstance(v,str):return redact(v)
  if isinstance(v,list):return [clean(x) for x in v]
  if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
  return v
 result=clean(data)
 if result.get('assistant_summary'):result['summary']=result['assistant_summary']
 result.setdefault('event_id','turn-'+uuid.uuid4().hex)
 result.update({'tool':'松伴连接器 · 显式选择回合','origin':'personal_agent','selected':True})
 if not isinstance(result.get('summary'),str) or not result['summary'].strip():raise ConnectorError('没有可同步的本轮项目内容。')
 if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>50000:raise ConnectorError('本轮摘要过长，请提炼关键内容，不要发送整段历史。')
 return result


def main(argv=None):
 parser=argparse.ArgumentParser(description='仅在显式选择松伴连接器的回合读取/同步团队内容')
 parser.add_argument('action',choices=['context','send']);parser.add_argument('--selected',action='store_true');parser.add_argument('--binding');parser.add_argument('--file')
 args=parser.parse_args(argv)
 if not args.selected:raise ConnectorError('本轮未标为显式选择，不读取或同步任何对话内容。')
 d=binding(args.binding)
 if args.action=='context':
  r=request(d,'/my-tasks');print(json.dumps({'team_id':d['team_id'],**r},ensure_ascii=False));return
 if args.file and Path(args.file).stat().st_size>60000:raise ConnectorError('输入过长，请勿发送整段历史。')
 raw=Path(args.file).read_text() if args.file else sys.stdin.read(60001)
 if len(raw)>60000:raise ConnectorError('输入过长，请勿发送整段历史。')
 try:data=payload(json.loads(raw))
 except (ValueError,TypeError):raise ConnectorError('本轮JSON摘要格式不正确，未上传。') from None
 r=request(d,'/conversation-notes',data)
 if not r.get('note_id'):raise ConnectorError('服务没有返回资料库记录号，不能确认已同步。')
 print(json.dumps({'synced':True,'note_id':r['note_id'],'report_id':r['report_id'],'duplicate':r.get('duplicate',False),'team_id':d['team_id'],'notice':'已同步到松伴团队资料库，团队智能体可读取；尚未独立验证事实。'},ensure_ascii=False))


if __name__=='__main__':
 try:main()
 except (ConnectorError,OSError) as e:print(json.dumps({'synced':False,'error':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
