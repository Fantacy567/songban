"""CORE-02 isolated TCP acceptance for task execution notes.

Mirror without .env, temporary SQLite and HOME, synthetic accounts, free loopback ports, and an explicit
protocol substitute instead of any model. Proves the data path, not real model quality. Never touches 8886.

    .venv/bin/python scripts/executable_tasks_acceptance.py
    .venv/bin/python D/src/scripts/executable_tasks_acceptance.py serve --dir D --port P   (internal)
"""
import argparse
import copy
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import continuous_sync_acceptance as staging  # noqa: E402

REPO = staging.REPO
T1_PROMPT = ('目标：验证姓名接口对正常姓名和空姓名的实际返回。已知依据：团队共同方向与主办方原文。'
             '边界：只发请求、不改代码；接口地址没有提供时先问队长，不要猜测路径。产物：两次请求的实际返回原文。验收：正常与空输入各一次，返回原样保存。')
HOSTILE = '<img src=x onerror="alert(1)"></textarea><script>alert(2)</script>'
MODES = {
    'missing_execution': lambda e: None,
    'steps_string': lambda e: {**e, 'steps': '启动后端然后发请求'},
    'too_many_steps': lambda e: {**e, 'steps': ['第%d步核对返回' % i for i in range(9)]},
    'empty_step': lambda e: {**e, 'steps': ['启动后端', '']},
    'long_text': lambda e: {**e, 'deliverable': '长' * 401},
}


def plan(ctx, mode):
    members, refs = ctx['members'], ctx['source_ids']
    p = {'summary': '协议替身草案（非真实模型）：先验证姓名接口，再录演示。',
         'findings': [{'topic': '接口地址', 'decision': '先向队长确认接口地址再验证。', 'reason': '资料里没有接口路径。', 'source_ids': ['direction'], 'needs_check': True}],
         'tasks': [{'key': 'T1', 'title': '验证姓名接口', 'owner_id': members[0]['id'], 'acceptance': '正常姓名与空姓名各请求一次并保存实际返回',
                    'depends_on': [], 'source_ids': ['direction'],
                    'execution': {'tool': '终端', 'steps': ['按团队已有启动说明启动后端', '发一次正常姓名请求', '发一次空姓名请求', '保存两次实际返回'],
                                  'ai_prompt': T1_PROMPT, 'deliverable': '两次请求的实际返回原文', 'help_hint': '写明卡在哪一步并贴出报错原文，向队长求助'}},
                   {'key': 'T2', 'title': '录制30秒演示', 'owner_id': members[-1]['id'], 'acceptance': '录屏能看到页面提交与返回',
                    'depends_on': ['T1'], 'source_ids': ['direction'] + refs[-1:],
                    'execution': {'tool': '浏览器与系统录屏', 'steps': ['等T1的返回通过检查', '打开页面提交一次正常姓名', '录下从提交到显示结果的过程'],
                                  'ai_prompt': '', 'deliverable': '一段约30秒的录屏', 'help_hint': '说明页面停在哪一步，附截图发到团队'}}],
         'questions': ['姓名接口的地址尚未提供，需要队长确认。']}
    if mode in MODES:
        p['tasks'][0]['execution'] = MODES[mode](p['tasks'][0]['execution'])
    elif mode == 'hostile':
        p['tasks'][0]['execution'].update(tool=HOSTILE, steps=[HOSTILE, '先向队长确认再操作'], ai_prompt=HOSTILE, deliverable=HOSTILE, help_hint=HOSTILE)
    return p


def serve(root, port):
    root = Path(root)
    if (REPO / '.env').exists():
        raise SystemExit('serve only from the staged mirror (no .env)')
    sys.path.insert(0, str(REPO))
    from app.main import create_app, digest, now
    from app.studio import hash_password
    import uvicorn

    def substitute(ctx):
        calls = root / 'model-calls'
        calls.write_text(str(int(calls.read_text() or 0) + 1) if calls.exists() else '1')
        return plan(ctx, (root / 'mode').read_text().strip() if (root / 'mode').exists() else 'good')
    db = root / 'acceptance.sqlite3'
    app = create_app(db, core_only=True, core_model_runner=substitute)
    with closing(sqlite3.connect(db)) as con:
        for m in json.loads((root / 'fixture.json').read_text()):
            con.execute('INSERT OR IGNORE INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',
                        (m['id'], m['phone'], m['name'], 'CORE-02合成验收', '', digest(m['token']), now(), hash_password(m['password'])))
        con.commit()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


class Server(staging.Server):
    def __init__(self, root, n):
        self.root, self.port = Path(root), staging.free_port()
        env = {'HOME': str(self.root / 'home'), 'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.log = (self.root / f'server-{n}.log').open('wb')
        self.proc = subprocess.Popen([sys.executable, str(self.root / 'src/scripts/executable_tasks_acceptance.py'), 'serve', '--dir', str(self.root), '--port', str(self.port)],
                                     cwd=self.root / 'src', env=env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(100):
            if self.proc.poll() is not None:
                raise SystemExit('isolated server exited; see server log')
            try:
                if self.call('GET', '/health')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        raise SystemExit('isolated server did not start')


def check(root, evidence_path):
    root = staging.stage(root)
    fx = {m['id']: m for m in json.loads((root / 'fixture.json').read_text())}
    ta, tb, tc = fx['core01-a']['token'], fx['core01-b']['token'], fx['core01-c']['token']
    db = root / 'acceptance.sqlite3'
    ev = {'date': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'scope': '隔离TCP服务、无.env镜像、临时数据库、合成账号；模型为协议替身，不证明真实模型拆解质量', 'steps': []}

    def step(name, ok, **detail):
        ev['steps'].append({'name': name, 'ok': bool(ok), **detail})
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)
        if not ok:
            raise AssertionError(name + ' ' + json.dumps(detail, ensure_ascii=False)[:2000])

    expected = {t['key']: t['execution'] for t in plan({'members': [{'id': 'x'}], 'source_ids': ['direction']}, 'good')['tasks']}
    execs = lambda tasks: {t['key']: t.get('execution') for t in tasks}
    servers = [Server(root, 1)]
    s = servers[0]
    try:
        team = s.call('POST', '/api/core/teams', ta, {'name': 'CORE-02合成团队'})[1]
        sid = team['id']
        base = '/api/core/teams/' + sid
        s.call('POST', '/api/core/join', tb, {'code': team['code']})
        s.call('POST', '/api/core/teams', tc, {'name': 'CORE-02另一团队'})
        rev = s.call('GET', base, ta)[1]['revision']
        st, _ = s.call('PUT', base + '/direction', ta, {'goal': '做出可演示的姓名登记页', 'rules': '合成主办方原文：提交可运行演示与30秒录屏。',
                                                        'rubric': '合成评分：功能可用、演示清楚。', 'non_goals': '', 'deadline': '', 'expected_revision': rev})
        s.call('PUT', base + '/profile', tb, {'strengths': '前端', 'willingness': '想练习演示', 'hours': 3})
        ev['port_1'] = s.port

        st, draft = s.call('POST', base + '/review', ta, {})
        step('合成输入经协议替身生成草案，每项任务带完整说明', st == 200 and execs(draft['body']['tasks']) == expected
             and draft['provenance'] == '协议测试替身，非真实模型', status=st)
        ev['draft_task_T1'] = draft['body']['tasks'][0]
        snap_b = s.call('GET', base, tb)[1]
        step('草案对同队成员可读，原有字段与来源保留', execs(snap_b['proposal']['body']['tasks']) == expected
             and all({'key', 'title', 'owner_id', 'acceptance', 'depends_on', 'source_ids'} <= set(t) for t in snap_b['proposal']['body']['tasks']))
        step('非队长不能发布', s.call('POST', base + '/proposals/' + draft['proposal_id'] + '/confirm', tb, {'expected_revision': snap_b['revision']})[0] == 403
             and s.call('GET', base, ta)[1]['plan_version'] == 0)
        step('其他团队不能读本队草案与任务', s.call('GET', base, tc)[0] == 403 and s.call('GET', base + '/my-tasks', tc)[0] == 403
             and s.call('GET', base + '/handoff.md', tc)[0] == 403)
        st, _ = s.call('POST', base + '/proposals/' + draft['proposal_id'] + '/confirm', ta, {'expected_revision': s.call('GET', base, ta)[1]['revision']})
        active = s.call('GET', base, tb)[1]
        step('队长确认后活动任务保留全部说明', st == 200 and active['plan_version'] == 1 and execs(active['active_plan']['tasks']) == expected)
        conn = s.call('POST', base + '/connections', tb, {'label': 'CORE-02合成插件'})[1]['token']
        mine_web = s.call('GET', base + '/my-tasks', tb)[1]['tasks']
        mine_plugin = s.call('GET', base + '/my-tasks', conn)[1]['tasks']
        step('成员网页与个人插件读取到本人任务说明', execs(mine_web) == {'T2': expected['T2']} and execs(mine_plugin) == {'T2': expected['T2']})
        st, md = s.call('GET', base + '/handoff.md', tb)
        needed = ['操作场景：终端', '1. 按团队已有启动说明启动后端', '4. 保存两次实际返回', T1_PROMPT, '要交的成果：两次请求的实际返回原文',
                  '卡住时：写明卡在哪一步', '操作场景：浏览器与系统录屏', '给个人AI的指令：不需要AI指令', '检查方法：正常姓名与空姓名各请求一次并保存实际返回']
        step('现有交接导出包含当前版本的说明字段', st == 200 and all(x in md for x in needed), missing=[x for x in needed if x not in md])
        md_before = md

        before = s.call('GET', base, ta)[1]
        for mode in MODES:
            (root / 'mode').write_text(mode)
            st, err = s.call('POST', base + '/review', ta, {})
            after = s.call('GET', base, ta)[1]
            step(f'非法说明（{mode}）整份草案不采用，原计划与草案不变，错误可见',
                 st == 502 and err['error']['code'] == 'invalid_execution' and after['plan_version'] == before['plan_version']
                 and after['active_plan']['tasks'] == before['active_plan']['tasks'] and after['proposal']['id'] == before['proposal']['id']
                 and '可照做的说明' in after['last_error'], status=st, code=(err.get('error') or {}).get('code') if isinstance(err, dict) else None)
        (root / 'mode').write_text('good')

        calls_before = (root / 'model-calls').read_text()
        s.call('PUT', base + '/automation', ta, {'enabled': True})
        st, note = s.call('POST', base + '/conversation-notes', conn, {'selected': True, 'event_id': 'core02-capture', 'user_message': '合成：记录这句话',
                                                                      'assistant_summary': '已记录', 'model_name': 'synthetic-model'})
        time.sleep(4)
        step('连接器上传仍只记录不分析（开启自动统筹也不调用替身）', st == 200 and note['analysis_triggered'] is False
             and (root / 'model-calls').read_text() == calls_before and s.call('GET', base, ta)[1]['proposal']['id'] == before['proposal']['id'])
        s.call('PUT', base + '/automation', ta, {'enabled': False})

        s.stop()
        s = Server(root, 2)
        servers.append(s)
        ev['port_2'] = s.port
        again = s.call('GET', base, tb)[1]
        st, md_after = s.call('GET', base + '/handoff.md', tb)
        step('隔离服务重启后草案、活动任务和导出说明不丢', execs(again['active_plan']['tasks']) == expected
             and execs(again['proposal']['body']['tasks']) == expected and md_after == md_before)

        legacy = copy.deepcopy(again['active_plan'])
        legacy = {k: legacy[k] for k in ('summary', 'findings', 'questions')} | {'tasks': [
            {k: t[k] for k in ('key', 'title', 'owner_id', 'acceptance', 'depends_on', 'source_ids')} for t in legacy['tasks']]}
        with closing(sqlite3.connect(db)) as con:
            con.execute('UPDATE core_settings SET active_plan=? WHERE squad_id=?', (json.dumps(legacy, ensure_ascii=False), sid))
            con.commit()
        old = s.call('GET', base, tb)[1]
        st, md_old = s.call('GET', base + '/handoff.md', tb)
        step('旧计划缺说明可读取并明确标记，不伪造说明', all('execution' not in t for t in old['active_plan']['tasks'])
             and md_old.count('操作说明：旧任务尚无操作说明') == 2 and '操作场景' not in md_old)
        logs = b''.join((root / f'server-{n}.log').read_bytes() for n in (1, 2))
        step('服务日志无异常堆栈', b'Traceback' not in logs)
    finally:
        for server in servers:
            server.stop()
    Path(evidence_path).parent.mkdir(parents=True, exist_ok=True)
    Path(evidence_path).write_text(json.dumps(ev, ensure_ascii=False, indent=2) + '\n')
    print('全部通过；证据写入', evidence_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', default='check', choices=('check', 'serve'))
    parser.add_argument('--dir')
    parser.add_argument('--port', type=int)
    parser.add_argument('--evidence', default=str(REPO / 'docs/reviews/core-02-evidence/tcp_acceptance.json'))
    args = parser.parse_args()
    if args.mode == 'serve':
        serve(args.dir, args.port)
    else:
        root = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix='songban-core02-'))
        try:
            check(root, args.evidence)
        finally:
            if not args.dir:
                shutil.rmtree(root, ignore_errors=True)
