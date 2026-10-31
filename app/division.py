"""Personalized coordination questions, member consent, and internal AI task publication."""
import hashlib,json
from datetime import datetime,timezone
from fastapi import Header
from pydantic import BaseModel,ConfigDict,Field

SCHEMA='''
CREATE TABLE IF NOT EXISTS division_rounds(id TEXT PRIMARY KEY,squad_id TEXT NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'waiting',attempts INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',plan_version INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS division_team ON division_rounds(squad_id);
CREATE TABLE IF NOT EXISTS division_answers(round_id TEXT NOT NULL,user_id TEXT NOT NULL,answers TEXT NOT NULL DEFAULT '[]',confirmed INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(round_id,user_id));
'''
def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)
def latest(con,sid):return con.execute('SELECT * FROM division_rounds WHERE squad_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
def start_round(con,sid,now,uid):
    direction=json.loads(con.execute('SELECT direction FROM core_settings WHERE squad_id=?',(sid,)).fetchone()[0])
    members=[r[0] for r in con.execute('SELECT user_id FROM squad_members WHERE squad_id=? ORDER BY rowid',(sid,))]
    fp=hashlib.sha256(dump([direction,members]).encode()).hexdigest();old=latest(con,sid)
    if old and old['fingerprint']==fp:return old['id']
    con.execute('UPDATE core_settings SET auto_review=0 WHERE squad_id=?',(sid,))
    ident=uid();con.execute('INSERT INTO division_rounds(id,squad_id,fingerprint,updated_at) VALUES(?,?,?,?)',(ident,sid,fp,now()))
    return ident

def role_question(strengths,willingness):
    profile=(willingness or '')+' '+(strengths or '')
    if any(word in profile for word in ['路演','表达','PPT','ppt']):return '你提到路演或表达。你这次更愿意负责讲解、展示材料，还是别的工作？具体想交付什么？'
    if any(word in profile for word in ['设计','界面','视觉']):return '你有设计相关经验。这次更愿意负责用户流程、界面草图，还是别的工作？具体想交付什么？'
    if any(word in profile for word in ['后端','代码','开发','编程']):return '你有开发相关经验。这次希望独立实现哪部分功能？哪些部分希望队友配合？'
    return '这次你最愿意承担哪部分工作？可以从了解用户、设计、实现、测试或展示中选，也可以提出其他职责。'
def questions(member,answers):
    return [role_question(member.get('strengths') or member.get('skills'),member.get('willingness')),
        '针对你刚才说的“'+(str(answers[0])[:180] if answers else '想承担的工作')+'”，哪些能独立完成，哪些需要AI或队友帮助？有什么不想承担的？',
        '从现在到截止时间，你实际还能投入多少小时？',
        '你希望交付什么具体成果？队友怎样检查才算完成？还有需要谁配合的地方吗？']
class Answer(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    round_id:str
    step:int=Field(ge=0,le=3)
    answer:str=Field(min_length=1,max_length=1600)


def register_division(api,db,access,problem,now,uid,review):
    def state(con,sid,user):
        row=latest(con,sid)
        if not row:return {'status':'not_started','members':[]}
        members=[dict(r) for r in con.execute('SELECT p.id,p.name,p.skills,c.strengths,c.willingness,c.hours FROM squad_members m JOIN people p ON p.id=m.user_id LEFT JOIN core_profiles c ON c.squad_id=m.squad_id AND c.user_id=m.user_id WHERE m.squad_id=? ORDER BY m.rowid',(sid,))]
        items=[];mine=None
        for member in members:
            data=con.execute('SELECT * FROM division_answers WHERE round_id=? AND user_id=?',(row['id'],member['id'])).fetchone()
            answers=json.loads(data['answers']) if data else [];confirmed=bool(data and data['confirmed'])
            items.append({'id':member['id'],'name':member['name'],'confirmed':confirmed,'answered':len(answers)})
            if member['id']==user:mine={'answers':answers,'confirmed':confirmed,'step':len(answers),'question':questions(member,answers)[len(answers)] if len(answers)<4 else None,'questions':questions(member,answers),'hours':member['hours']}
        status=row['status']
        if status=='running' and (datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])).total_seconds()>180:status='unknown'
        return {'round_id':row['id'],'status':status,'members':items,'me':mine,'error':row['error'],'plan_version':row['plan_version'],'all_confirmed':bool(items and all(m['confirmed'] for m in items))}
    def publish(sid,user,retry_unknown=False):
        with db(True) as con:
            data=state(con,sid,user)
            if not data.get('all_confirmed'):return data
            if data['status']=='published':return data
            if data['status']=='running':return data
            if data['status']=='unknown' and not retry_unknown:raise problem(409,'division_unknown','上次生成结果未知，请明确选择重试；不会自动重复调用。')
            row=latest(con,sid)
            if not con.execute('SELECT 1 FROM core_profiles c JOIN squad_members m ON c.squad_id=m.squad_id AND c.user_id=m.user_id WHERE c.squad_id=? AND c.hours>0',(sid,)).fetchone():raise problem(409,'division_no_capacity','全员可投入时间为0，请先修改自己的回答。')
            if row['attempts']>=5:raise problem(429,'division_attempt_limit','本轮已尝试5次，请先检查模型服务；回答已保存。')
            con.execute("UPDATE division_rounds SET status='running',attempts=attempts+1,error='',updated_at=? WHERE id=?",(now(),row['id']))
            round_id=row['id'];attempt=row['attempts']+1
        try:
            result=review(sid,user)
            with db(True) as con:
                current=latest(con,sid);settings=con.execute('SELECT revision,plan_version FROM core_settings WHERE squad_id=?',(sid,)).fetchone()
                if current['id']!=round_id or current['attempts']!=attempt or current['status']!='running' or state(con,sid,user)['all_confirmed'] is not True:raise problem(409,'division_changed','共同方向或成员已变化，请重新协调。')
                if settings['revision']!=result['base_revision']:raise problem(409,'division_changed','生成时资料更新，任务未发布；请核对后重试。')
                plan=result['body'];owners={task['owner_id'] for task in plan['tasks']}
                hours={r['user_id']:r['hours'] for r in con.execute('SELECT user_id,hours FROM core_profiles WHERE squad_id=?',(sid,))}
                if any(hours.get(owner,0)<=0 for owner in owners):raise problem(502,'division_capacity','AI把任务分配给了没有可投入时间的成员，未发布。')
                required={m['id'] for m in state(con,sid,user)['members'] if hours.get(m['id'],0)>0}
                if not required.issubset(owners):raise problem(502,'division_missing_member','AI遗漏了已确认可参与的队员，未发布；可重试。')
                version=settings['plan_version']+1
                con.execute('INSERT INTO core_plan_history(squad_id,version,body,confirmed_by,created_at) VALUES(?,?,?,?,?)',(sid,version,dump(plan),'internal-ai:member-confirmed',now()))
                con.execute('UPDATE core_proposals SET confirmed_at=? WHERE id=?',(now(),result['proposal_id']))
                con.execute('UPDATE core_settings SET active_plan=?,plan_version=?,revision=revision+1,updated_at=? WHERE squad_id=?',(dump(plan),version,now(),sid))
                con.execute("UPDATE division_rounds SET status='published',plan_version=?,updated_at=? WHERE id=?",(version,now(),round_id))
        except Exception as error:
            with db(True) as con:con.execute("UPDATE division_rounds SET status='failed',error=?,updated_at=? WHERE id=? AND attempts=? AND status='running'",(getattr(error,'message','AI未能生成有效任务，所有回答与确认已保留。'),now(),round_id,attempt))
        with db() as con:return state(con,sid,user)
    @api.get('/api/core/teams/{sid}/division')
    def get(sid:str,authorization:str=Header(default='')):
        with db() as con:user,_=access(con,sid,authorization,connector=False);return state(con,sid,user['id'])
    @api.post('/api/core/teams/{sid}/division/answers')
    def answer(sid:str,body:Answer,authorization:str=Header(default='')):
        if not body.answer.strip():raise problem(422,'division_empty','请先回答当前问题。')
        if body.step==2:
            try:hours=float(body.answer)
            except ValueError:raise problem(422,'division_hours','请输入0到168之间的小时数。') from None
            if not 0<=hours<=168:raise problem(422,'division_hours','请输入0到168之间的小时数。')
        with db(True) as con:
            user,_=access(con,sid,authorization,connector=False);data=state(con,sid,user['id'])
            if data.get('round_id')!=body.round_id or data['me']['step']!=body.step or data['me']['confirmed']:raise problem(409,'division_stale','问答已更新，请读取当前问题。')
            if data['status'] in ('running','published'):raise problem(409,'division_locked','任务正在生成或已发布。')
            answers=data['me']['answers']+[body.answer.strip()]
            con.execute('INSERT INTO division_answers VALUES(?,?,?,0) ON CONFLICT(round_id,user_id) DO UPDATE SET answers=excluded.answers',(body.round_id,user['id'],dump(answers)))
            return state(con,sid,user['id'])
    @api.post('/api/core/teams/{sid}/division/confirm')
    def confirm(sid:str,body:dict,authorization:str=Header(default='')):
        with db(True) as con:
            user,_=access(con,sid,authorization,connector=False);data=state(con,sid,user['id'])
            if not data.get('round_id') or body.get('round_id')!=data.get('round_id') or body.get('confirmed') is not True or data['me']['step']!=4:raise problem(409,'division_incomplete','请完成问答并确认本人的职责与时间。')
            if not data['me']['confirmed']:
                answers=data['me']['answers']
                con.execute('UPDATE division_answers SET confirmed=1 WHERE round_id=? AND user_id=?',(data['round_id'],user['id']))
                old=con.execute('SELECT strengths FROM core_profiles WHERE squad_id=? AND user_id=?',(sid,user['id'])).fetchone()
                con.execute('INSERT INTO core_profiles(squad_id,user_id,strengths,willingness,hours) VALUES(?,?,?,?,?) ON CONFLICT(squad_id,user_id) DO UPDATE SET willingness=excluded.willingness,hours=excluded.hours',(sid,user['id'],old['strengths'] if old else '',answers[0]+'；能力边界：'+answers[1]+'；交付与检查：'+answers[3],float(answers[2])))
                con.execute('UPDATE core_settings SET revision=revision+1 WHERE squad_id=?',(sid,))
        return publish(sid,user['id'])
    @api.post('/api/core/teams/{sid}/division/reset')
    def reset(sid:str,body:dict,authorization:str=Header(default='')):
        with db(True) as con:
            user,_=access(con,sid,authorization,connector=False);data=state(con,sid,user['id'])
            if not data.get('round_id') or body.get('round_id')!=data.get('round_id') or data['status'] in ('running','published'):raise problem(409,'division_locked','任务生成中或已发布时不能覆盖分工回答。')
            con.execute('DELETE FROM division_answers WHERE round_id=? AND user_id=?',(data['round_id'],user['id']))
            con.execute("UPDATE division_rounds SET status='waiting',error='' WHERE id=?",(data['round_id'],))
            con.execute('UPDATE core_settings SET revision=revision+1 WHERE squad_id=?',(sid,))
        return {'reset':True}
    @api.post('/api/core/teams/{sid}/division/publish')
    def retry(sid:str,body:dict,authorization:str=Header(default='')):
        with db() as con:user,_=access(con,sid,authorization,connector=False)
        return publish(sid,user['id'],body.get('retry_unknown') is True)
