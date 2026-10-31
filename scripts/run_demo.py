"""Run the prefilled, entirely synthetic Songban walkthrough on loopback.

python scripts/run_demo.py --port 8898
Uses a fresh .browser-cache/demo/<run>/demo.sqlite3; never opens the main DB. Parent reports alone call the configured real model.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from datetime import datetime
from contextlib import closing
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONTENT = json.loads((ROOT / 'static/songban-demo-content.json').read_text(encoding='utf-8'))
PEOPLE = [tuple(person[key] for key in ('key', 'name', 'role', 'strengths', 'willingness')) for person in CONTENT['people']]
RULES = CONTENT['rules']
DIRECTION = {key: CONTENT[key] for key in ('goal', 'rules', 'rubric', 'non_goals')}
TASK_ROWS = [
    (0, '梳理使用场景', 'accepted'), (0, '完成页面草图', 'accepted'),
    (0, '连接交互原型', 'in_progress'),
    (1, '搭建页面结构', 'accepted'), (1, '接入活动与任务数据', 'reported_done'),
    (4, '整理试用反馈', 'blocked'),
    (2, '准备访谈问题', 'accepted'), (2, '整理同学反馈', 'accepted'),
    (4, '设计试用问卷', 'reported_done'),
    (3, '验证主流程', 'in_progress'), (3, '核对更新后的原型', 'blocked'), (3, '录制作品演示', 'todo'),
]
TOPICS = [
    ('校园活动搭子', '我想让同学按兴趣找到活动，再和伙伴组队完成小作品。', '可以先做兴趣选择、活动推荐和组队分工三个步骤。林同学做原型、周同学实现页面，其他队友整理资料和验证。优势是团队分工匹配；问题是活动信息需要维护，推荐效果要用真实试用反馈验证。'),
    ('校园排队助手', '食堂窗口排队太久，想做一个排队时间提示工具。', '可以先让同学手动报告排队情况，展示最近更新时间。页面开发可由周同学负责。问题是缺少实时数据和持续投稿，不能把估计时间当实时结果，需要现场试点。'),
    ('校园互助地图', '我想把闲置交换、学习互助和校内活动放进一张地图。', '需求直观，适合访谈和内容整理。但地图定位、隐私与多类信息会扩大范围。先保留一个互助类别，用列表原型验证需求，再决定是否接地图。'),
    ('演示彩排助手', '我想给队伍做一个一分钟路演计时和检查工具。', '许同学擅长演练，可以做计时、讲稿分段和交付清单。优势是周末能做出完整演示；问题是差异化较弱，需要证明相较普通计时器的价值。'),
    ('活动反馈小助手', '活动结束后反馈很多，想把问卷意见整理为可执行的改进建议。', '吴同学可以设计问卷，陈同学核对意见分类。先用匿名样例展示分类和来源。优势是数据能力匹配；问题是样本偏差和隐私，需要实际授权的数据验证。'),
]


def demo_ranking(context):
    """Prewritten demonstration assessments, never a live model or fallback."""
    by_title={title:index for index,(title,_,_) in enumerate(TOPICS)}
    items=[]
    for candidate in sorted(context['candidates'],key=lambda c:by_title.get(c['title'],99)):
        index=by_title.get(candidate['title'],0)
        items.append({'candidate_id':candidate['id'], 'dimensions':{
            'team_fit':'【模拟评估】产品、前端、调研、测试和运营五类能力可以分别承担工作。',
            'track_fit':'【模拟评估】符合校园生活与周末原型的演示范围，正式参赛仍需核对赛规。',
            'advantage':TOPICS[index][2].split('。')[0]+'。',
            'rubric_fit':'【模拟评估】围绕需求清晰、流程可用和表达组织成果，评分比例为演示设定。',
            'feasibility':'【模拟评估】先完成一个可点击的小闭环，再安排同伴检查和一分钟展示。'},
            'advantages':['成员能力能覆盖原型、实现、内容和验证','可以在周末范围内展示核心流程'],
            'risks':[TOPICS[index][2],'样例讨论不能证明真实用户愿意使用'],
            'verification':['访谈三位目标同学','核对活动要求并验证核心操作'],
            'source_ids':[candidate['turns'][0]['id'],'track','rubric']})
    return {'summary':'【模拟排名】优先展示校园活动搭子方案，再比较其他候选的范围与验证成本。所有评价都是预设演示内容。', 'items':items,
            'requested_model':'songban-demo','actual_model':'songban-demo（预设内容）'}


def demo_plan(context):
    members = context['members']
    by_id = {m['id']: m for m in members}
    ordered = [by_id['demo-' + p[0]] for p in PEOPLE if 'demo-' + p[0] in by_id]
    ordered += [m for m in members if m not in ordered]
    return {'summary': '【模拟统筹】先明确场景，再完成页面、内容和展示；每个人都有可检查的成果。',
            'findings': [{'topic': '本轮分工', 'decision': '围绕校园活动搭子的完整流程协作。', 'reason': '示例按成员意愿和能力安排。', 'source_ids': ['direction'], 'needs_check': True}],
            'tasks': [{'key': f'T{i + 1}', 'title': title, 'owner_id': ordered[owner % len(ordered)]['id'],
                       'acceptance': '【演示验收目标】' + CONTENT['task_details'][title] + ' 由另一位队友逐项核对这些交付内容，并记录缺项或通过结论。',
                       'depends_on': [], 'source_ids': ['direction']} for i, (owner, title, _) in enumerate(TASK_ROWS)],
            'questions': ['演示示例已准备好；实际参赛时请重新核对主办方要求。']}


def demo_materials(context):
    items = []
    for source in context['sources']:
        for segment in source['segments']:
            for line in segment['text'].splitlines():
                if line.strip():
                    items.append({'category': '队员想法' if '群聊' in segment['text'] or '模拟聊天' in line else '活动要求', 'text': line, 'kind': 'statement', 'importance': 'normal',
                                  'citations': [{'source_id': source['id'], 'segment_id': segment['id'], 'quote': line}],
                                  'member_ids': [], 'conflict': ''})
    return {'summary': '【模拟整理】活动要求、团队想法和交付清单已经放在一起。', 'items': items[:40]}


def demo_workbench(context):
    role = context.get('role', {})
    role_id = role.get('id', 'direction') if isinstance(role, dict) else role
    paragraphs = CONTENT['workbench']
    return {'text': '【模拟回复 · 未调用真实模型】\n\n' + paragraphs.get(role_id, paragraphs['direction']) + '\n\n这些是预设的演示建议，你可以修改、共享或继续下一步。',
            'mode': 'fixture', 'requested_model': 'songban-demo', 'actual_model': 'songban-demo',
            'actions': [{'type': 'prepare_direction', 'label': '查看方向草稿', 'fields': DIRECTION},
                        {'type': 'share_turn', 'label': '预览共享本轮内容'},
                        {'type': 'open_page', 'label': '继续查看任务', 'page': 'tasks'}]}


def build_demo(db_path, *, resume=None, parent_report_config=None, parent_report_runner=None):
    # The caller chooses a new dedicated DB before app.main's module-level app is imported.
    from app.main import create_app, digest, now
    from fastapi.testclient import TestClient
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    app = create_app(db_path, core_only=True, enforce_journey=False, core_model_runner=demo_plan,
                     materials_model_runner=demo_materials, workbench_model_runner=demo_workbench, topic_model_runner=demo_ranking,
                     parent_report_options={'config': parent_report_config or {}, 'runner': parent_report_runner, 'event': CONTENT.get('event', {}), 'demo': True})
    users = []
    if resume:
        users.extend(resume['users'])
        with closing(sqlite3.connect(db_path)) as con:
            for user in users:
                row=con.execute('SELECT token_hash FROM people WHERE id=?',(user['id'],)).fetchone()
                if not row or row[0]!=digest(user['token']):
                    raise RuntimeError('Demo resume identity does not match this database.')
    else:
        with closing(sqlite3.connect(db_path)) as con:
            for key, name, role, strengths, willingness in PEOPLE:
                ident, token = 'demo-' + key, secrets.token_urlsafe(32)
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,phone_real) VALUES(?,?,?,?,?,?,?,0)',
                            (ident, ident, name, '虚构演示成员 · ' + role, strengths, digest(token), now()))
                con.execute('INSERT INTO core_guest_people VALUES(?,?)', (ident, now()))
                users.append({'id': ident, 'token': token, 'name': name, 'role': role, 'strengths': strengths, 'willingness': willingness})
            con.commit()
    deadline = CONTENT['deadline']
    bootstrap = {}
    @app.middleware('http')
    async def demo_only(request, call_next):
        path = request.url.path
        if path in ('/', '/learning', '/demo', '/static/songban.html'):
            html = (ROOT / 'static/songban.html').read_text(encoding='utf-8')
            html = html.replace('<head>', '<head>\n<script src="/demo/bootstrap.js"></script>\n<link rel="stylesheet" href="/static/songban-demo.css?v=1">')
            html = html.replace('</head>', '<script defer src="/static/songban-demo.js?v=1"></script>\n</head>')
            return HTMLResponse(html, headers={'Cache-Control': 'no-store'})
        if path == '/demo/bootstrap.js':
            code = 'window.SongbanDemo=' + json.dumps(bootstrap, ensure_ascii=False) + ';\n'
            code += '''const demo=window.SongbanDemo;
let actor=sessionStorage.getItem('songban-demo-actor');
if(!demo.users.some(u=>u.id===actor))actor=demo.users[0].id;
localStorage.setItem('studio-token',demo.users.find(u=>u.id===actor).token);
const savedTeam=localStorage.getItem('studio-squad');
localStorage.setItem('studio-squad',[demo.team.id,demo.topic_team.id].includes(savedTeam)?savedTeam:demo.topic_team.id);
sessionStorage.removeItem('songban-personal');
if(!location.hash)location.hash='/onboarding';
'''
            return Response(code, media_type='text/javascript', headers={'Cache-Control': 'no-store'})
        if path == '/api/core/install-options':
            return JSONResponse({'available': True, 'project_dir': '校园活动搭子（模拟项目）', 'notice': '演示连接流程，仅生成模拟回执。'})
        if path.endswith('/install') and request.method == 'POST':
            return JSONResponse({'kind': 'demo', 'tool': '演示工具', 'project_dir': '校园活动搭子（模拟项目）',
                                 'config_file': '演示配置', 'backup_dir': '演示备份', 'notice': '【模拟连接成功】没有安装插件，也没有修改电脑上的配置。'})
        if path.startswith('/api/studio/') or path.startswith('/api/workflow'):
            return JSONResponse({'error': {'code': 'demo_only', 'message': '本页使用模拟成员，请在顶部切换演示角色。'}}, status_code=403)
        if path.startswith('/api/materials/') and path.endswith('/sources') and request.method == 'POST':
            body = await request.json()
            if body.get('kind') == 'url':
                # A simulated link must never start a real outbound crawl.
                body.update(kind='text', nature='sample', content='【模拟网页内容】\n' + RULES)
                request._body = json.dumps(body).encode('utf-8')
        return await call_next(request)


    if resume:
        team, topic_team = resume['team'], resume['topic_team']
    else:
        with TestClient(app) as client:
            def call(method, url, body=None, actor=0):
                r = client.request(method, url, headers={'Authorization': 'Bearer ' + users[actor]['token']},
                                   **({'json': body} if body is not None else {}))
                if not r.is_success:
                    raise RuntimeError(f'Demo setup {url}: {r.status_code} {r.text}')
                return r.json()

            team = call('POST', '/api/core/teams', {'name': '校园创作小队 · 全流程演示'})
            base = '/api/core/teams/' + team['id']
            for index, user in enumerate(users):
                if index:
                    call('POST', '/api/core/join', {'code': team['code']}, index)
                call('PUT', base + '/profile', {'strengths': user['strengths'], 'willingness': user['willingness'], 'hours': 8}, index)
                call('PUT', '/api/core/me/preferences', {'interests': ['校园生活', '音乐'], 'skills': ['画画或设计', '整理资料'],
                     'time': '一个周末', 'city': '上海', 'experience': CONTENT['people'][index]['experience'], 'expected_revision': 0}, index)
            snap = call('GET', base)
            call('PUT', base + '/direction', {**DIRECTION, 'deadline': deadline, 'expected_revision': snap['revision']})
            plan = call('POST', base + '/review', {})
            call('POST', base + '/proposals/' + plan['proposal_id'] + '/confirm', {'expected_revision': plan['base_revision']})
            for i, (owner, title, status) in enumerate(TASK_ROWS):
                if status == 'todo':
                    continue
                report = call('POST', base + '/reports', {'event_id': f'demo-seed-{i}', 'tool': '模拟成员记录', 'origin': 'human',
                    'task_key': f'T{i + 1}', 'plan_version': 1, 'status': 'reported_done' if status == 'accepted' else status,
                    'summary': f'【模拟进展】{title}：' + CONTENT['task_details'][title],
                    'blocker': '等待产品与前端确认同一版原型，请林同学核对推荐理由和返回按钮文案。' if status == 'blocked' else '',
                    'evidence': ['【模拟成果记录】' + CONTENT['task_details'][title]]}, owner)
                if status == 'accepted':
                    snap = call('GET', base)
                    call('POST', base + f'/tasks/T{i + 1}/check', {'expected_revision': snap['revision'], 'plan_version': 1,
                         'report_id': report['report_id'], 'verdict': 'accepted', 'note': '【模拟检查】已按「' + title + '」的交付清单核对内容完整性，未发现缺项；试用结论仍需正式用户验证。'}, (owner + 1) % len(users))
            topic_team=call('POST','/api/core/teams',{'name':'校园创作小队 · 五人选题演示'})
            for index,user in enumerate(users):
                if index:call('POST','/api/core/join',{'code':topic_team['code']},index)
                call('PUT','/api/core/teams/'+topic_team['id']+'/profile',{'strengths':user['strengths'],'willingness':user['willingness'],'hours':8},index)
            for index in range(len(users)):
                for scope in (None, team['id'], topic_team['id']):
                    space = call('GET', '/api/materials/space' + ('?team_id=' + scope if scope else ''), actor=index)
                    material_base = '/api/materials/spaces/' + space['id']
                    if not space['sources']:
                        for n, (name, content) in enumerate([('教育 Agent 创作周末 · 虚构赛规', RULES), ('小队讨论 · 虚构群聊', CONTENT['chat'])]):
                            source = call('POST', material_base + '/sources', {'request_id': f'seed-{index}-{scope}-{n}', 'kind': 'text', 'name': name, 'content': content, 'nature': 'sample'}, index)['source']
                            rev = call('GET', material_base, actor=index)['revision']
                            call('POST', material_base + '/sources/' + source['id'] + '/parse', {'expected_revision': rev}, index)
                        rev = call('GET', material_base, actor=index)['revision']
                        call('POST', material_base + '/generate', {'request_id': 'seed-organize', 'expected_revision': rev}, index)
                    session = call('POST', '/api/workbench/sessions', {'request_id': f'seed-session-{index}-{scope}', 'title': '校园活动搭子 · 示例讨论', 'team_id': scope}, index)['session']['id']
                    call('POST', '/api/workbench/sessions/' + session + '/turns', {'request_id': 'seed-turn', 'text': CONTENT['prompt'], 'role_id': 'direction', 'source_ids': []}, index)
                    # Keep the voting team undecided until its round starts. Sharing a
                    # discussion here would already create an idea-board workflow.
                    if scope == team['id']:
                        history = call('GET', '/api/workbench/sessions/' + session, actor=index)
                        message = next(m for m in history['messages'] if m['role'] == 'assistant')
                        call('POST', '/api/workbench/sessions/' + session + '/share', {'request_id': 'seed-share', 'message_id': message['id'],
                             'team_id': scope, 'summary': f'【模拟共享】{users[index]["name"]}：' + users[index]['willingness'] + '\n' + CONTENT['share'], 'selected': True}, index)
                call('POST', base + '/connections', {'label': users[index]['name'] + '的演示工具'}, index)

    bootstrap.update(users=users, team=team, topic_team=topic_team, direction={**DIRECTION, 'deadline': deadline}, rules=RULES, parent_reports=True)

    from fastapi import Header
    @app.post('/demo/advance')
    def advance(body:dict,authorization:str=Header(default='')):
        actor=next((i for i,u in enumerate(users) if authorization=='Bearer '+u['token']),None)
        if actor is None:return JSONResponse({'error':{'message':'请使用演示成员。'}},status_code=401)
        sid=body.get('team_id')
        if sid not in (team['id'],topic_team['id']):
            return JSONResponse({'error':{'message':'请选择顶部的五人选题或任务进度演示小队。'}},status_code=422)
        action=body.get('action')
        if action not in ('upload','confirm_next','vote_others','claim_others'):
            return JSONResponse({'error':{'message':'未知演示操作。'}},status_code=422)
        base='/api/core/teams/'+sid
        with TestClient(app) as demo_client:
            def invoke(method,suffix,payload=None,index=actor):
                response=demo_client.request(method,base+suffix,headers={'Authorization':'Bearer '+users[index]['token']},
                    **({'json':payload} if payload is not None else {}))
                if not response.is_success:
                    from fastapi import HTTPException
                    raise HTTPException(response.status_code,response.json().get('error',{}).get('message','演示步骤未完成'))
                return response.json()
            def operation(action,index,extra,revision):
                return invoke('POST',action,{'request_id':'demo-'+secrets.token_hex(12),'expected_revision':revision,**extra},index)
            current=invoke('GET','/topic-selection')['round']
            if not current:
                return JSONResponse({'error':{'message':'请先点击“开启选题讨论”，表单已填好。'}},status_code=409)
            if action=='upload':
                for index,(title,user_text,reply) in enumerate(TOPICS):
                    invoke('POST','/topic-selection/turns',{'round_id':current['id'],'event_id':'demo-topic-'+users[index]['id'],
                        'selected':True,'topic_title':title,'user_message':'【模拟成员发言】'+user_text,
                        'assistant_message':'【模拟 AI 可见回复】'+reply,'model_name':'songban-demo（预设内容）'},index)
                notice='5 位模拟成员的选题对话已准备好，可逐个确认。'
            elif action=='confirm_next':
                member=next((m for m in current['members'] if m['id']!=users[actor]['id'] and not m['confirmed']),None)
                if member:
                    index=next(i for i,u in enumerate(users) if u['id']==member['id'])
                    operation('/topic-selection/ready',index,{'complete':True},current['revision'])
                notice='一位模拟队友已确认。你自己的确认仍由页面按钮完成。' if member else '其他模拟队友都已确认，请点击本人的“确认进入排名”。'
            elif action=='vote_others':
                if current['phase']!='voting':return JSONResponse({'error':{'message':'请先完成全员确认并进入投票。'}},status_code=409)
                chosen=current['my_vote'] or current['eligible'][0]
                for index,user in enumerate(users):
                    current=invoke('GET','/topic-selection')['round']
                    if user['id']==users[actor]['id'] or current['phase']!='voting':continue
                    member=next(m for m in current['members'] if m['id']==user['id'])
                    if not member['voted']:operation('/topic-selection/votes',index,{'candidate_id':chosen,'ballot':current['ballot']},current['revision'])
                notice='其他模拟队友已投票；本轮演示让队友选择与你相同的方向。'
            else:
                snapshot=invoke('GET','')
                for task in snapshot['active_plan'].get('tasks',[]):
                    index=next((i for i,u in enumerate(users) if u['id']==task.get('suggested_owner_id')),None)
                    if index is None or index==actor or task['owner_id'] or not task.get('claim_required'):continue
                    snapshot=invoke('GET','')
                    operation('/tasks/'+task['key']+'/claim',index,{},snapshot['revision'])
                notice='模拟队友已按建议领取各自任务，你可以领取剩余任务。'
        return {'simulated':True,'notice':notice}


    return app


if __name__ == '__main__':
    import uvicorn
    from app import environment
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8898)
    parser.add_argument('--resume', help='Private resume manifest containing the existing demo DB and bootstrap identities')
    args = parser.parse_args()
    # Capture only the report's model configuration before clearing demo services.
    environment.load_env()
    from app.planner import team_model_config
    parent_report_config = team_model_config()
    allowed_model_hosts = os.environ.get('MODEL_ALLOWED_HOSTS')
    resume = None
    if args.resume:
        receipt = json.loads(Path(args.resume).read_text(encoding='utf-8-sig'))
        db = Path(receipt['db']).resolve()
        if not db.is_file(): raise SystemExit('The existing demo database was not found.')
        folder = db.parent
        resume = receipt['bootstrap']
    else:
        folder = ROOT / '.browser-cache/demo' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
        folder.mkdir(parents=True)
        db = folder / 'demo.sqlite3'
    for key in environment.ENV_KEYS:
        os.environ.pop(key, None)
    if allowed_model_hosts: os.environ['MODEL_ALLOWED_HOSTS'] = allowed_model_hosts
    os.environ['DATABASE_PATH'] = str(db)
    with patch('app.environment.load_env'):
        app = build_demo(db, resume=resume, parent_report_config=parent_report_config)
    (folder / 'runtime.json').write_text(json.dumps({'pid': os.getpid(), 'port': args.port, 'db': str(db)}, ensure_ascii=False), encoding='utf-8')
    print(f'Songban demo: http://127.0.0.1:{args.port}/#/onboarding', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
