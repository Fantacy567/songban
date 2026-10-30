"""Authenticated, paged evidence archive. Retrieval returns records, not invented answers."""
import json
from fastapi import Header, Query

STAGE_SQL = "COALESCE(json_extract(r.body,'$.recorded_stage'),CASE WHEN COALESCE(json_extract(r.body,'$.plan_version'),0)>0 THEN 'development' ELSE 'discussion' END)"
JOIN_SQL = 'FROM library_notes l JOIN core_reports r ON r.id=l.id JOIN people p ON p.id=l.author_id LEFT JOIN core_connections c ON c.id=r.connection_id'


def library_counts(con, sid):
    row = con.execute(f"SELECT COUNT(*) AS total,MAX(r.seq) AS latest_seq,COUNT(DISTINCT l.author_id) AS contributors {JOIN_SQL} WHERE l.squad_id=?", (sid,)).fetchone()
    return {'total':row['total'],'latest_seq':row['latest_seq'] or 0,'contributors':row['contributors']}


def record(row, brief=False):
    payload=json.loads(row['report_body'])
    reply=payload.get('assistant_message') or payload.get('assistant_summary') or payload.get('summary') or ''
    full=bool(payload.get('assistant_message'))
    user=payload.get('user_message') or payload.get('excerpt') or ''
    if brief:
        payload.pop('assistant_message',None)
        if 'user_message' in payload:payload['user_message']=user[:1000]
    return {'source_label':row['source_label'] or '网页手动补充','source_kind':'manual' if row['connection_id'].startswith('web:') else 'connector','user_preview':user[:1000] if brief else user,'reply_preview':reply[:1000] if brief else reply,'content_truncated':brief and (len(user)>1000 or len(reply)>1000),'reply_length':len(reply),'id':row['id'],'seq':row['seq'],'squad_id':row['squad_id'],'author_id':row['author_id'],
            'author':row['author'],'created_at':row['created_at'],'body':row['body'][:1000] if brief else row['body'],
            'stage':row['stage'],'reply_kind':'full' if full else 'summary',
            'report':{**payload,'user_name':row['author']}}


def register_library(api, db, access, problem):
    def filters(sid,q,author_id,stage,task_key):
        if len(q)>200 or len(author_id)>120 or len(task_key)>32:
            raise problem(422,'invalid_library_filter','检索文字过长，请缩短后重试。')
        if stage and stage not in ('discussion','development','recap'):
            raise problem(422,'invalid_library_filter','请选择选题讨论、任务执行或赛后复盘。')
        parts=['l.squad_id=?'];args=[sid]
        if author_id:parts.append('l.author_id=?');args.append(author_id)
        if stage:parts.append(STAGE_SQL+'=?');args.append(stage)
        if task_key:parts.append("json_extract(r.body,'$.task_key')=?");args.append(task_key)
        if q.strip():
            # Literal matching: %, _ and SQL syntax have no special meaning.
            parts.append("instr(lower(p.name||' '||l.body||' '||COALESCE(json_extract(r.body,'$.assistant_message'),'')||' '||COALESCE(json_extract(r.body,'$.model_name'),'')),lower(?))>0")
            args.append(q.strip())
        return ' AND '.join(parts),args

    @api.get('/api/core/teams/{sid}/library')
    def library(sid:str,brief:bool=False,q:str='',author_id:str='',stage:str='',task_key:str='',cursor:int|None=Query(default=None,ge=1),limit:int=Query(default=20,ge=1,le=50),authorization:str=Header(default='')):
        with db() as con:
            access(con,sid,authorization)
            where,args=filters(sid,q,author_id,stage,task_key)
            total=con.execute(f'SELECT COUNT(*) {JOIN_SQL} WHERE {where}',args).fetchone()[0]
            paging=where+(' AND r.seq<?' if cursor is not None else '')
            paged=args+([cursor] if cursor is not None else [])+[limit+1]
            rows=con.execute(f'SELECT l.*,r.seq,r.connection_id,r.body AS report_body,c.label AS source_label,p.name AS author,{STAGE_SQL} AS stage {JOIN_SQL} WHERE {paging} ORDER BY r.seq DESC LIMIT ?',paged).fetchall()
            more=len(rows)>limit;items=[record(r,brief) for r in rows[:limit]]
            counts=library_counts(con,sid)
        return {'items':items,'total':total,'stats':counts,'next_cursor':items[-1]['seq'] if more else None,
                'notice':'只检索本队获准共享的记录。原文与历史摘要分别标注；记录不等于成果已经验收。'}

    @api.get('/api/core/teams/{sid}/library/{note_id}')
    def library_record(sid:str,note_id:str,authorization:str=Header(default='')):
        with db() as con:
            access(con,sid,authorization)
            row=con.execute(f'SELECT l.*,r.seq,r.connection_id,r.body AS report_body,c.label AS source_label,p.name AS author,{STAGE_SQL} AS stage {JOIN_SQL} WHERE l.squad_id=? AND l.id=?',(sid,note_id)).fetchone()
        if not row:raise problem(404,'record_not_found','本队没有这条可查看的记录。')
        return record(row)
