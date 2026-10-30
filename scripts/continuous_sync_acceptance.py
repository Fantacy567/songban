"""CORE-01 isolated TCP acceptance for continuous Codex sync.

Runs a mirror of app/ static/ plugins/ scripts/ without .env, a temporary SQLite database,
a temporary HOME holding synthetic Codex logs, and free loopback ports. Never touches 8886.

    .venv/bin/python scripts/continuous_sync_acceptance.py            # full TCP check
    .venv/bin/python scripts/continuous_sync_acceptance.py stage --dir D
    .venv/bin/python D/src/scripts/continuous_sync_acceptance.py serve --dir D --port P
"""
import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SESSION_A = 'synthetic-core01-session-a'
SESSION_B = 'synthetic-core01-session-b'
FAKE = 'sk-' + 'synthetic' + '0' * 12  # assembled at runtime; not a real key
MEMBERS = [('core01-a', '甲·合成成员', '18000000301'), ('core01-b', '乙·合成成员', '18000000302'),
           ('core01-c', '丙·另队成员', '18000000303')]


def append(path, *items):
    with Path(path).open('ab') as f:
        for item in items:
            f.write((json.dumps(item, ensure_ascii=False) + '\n').encode())


def message(role, text, **extra):
    kind = 'input_text' if role == 'user' else 'output_text'
    return {'type': 'response_item', 'payload': {'type': 'message', 'role': role, 'content': [{'type': kind, 'text': text}], **extra}}


def codex_turn(path, turn_id, user, reply, model='synthetic-model-x1'):
    items = [{'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': turn_id}}]
    if model:
        items.append({'type': 'turn_context', 'payload': {'model': model}})
    items += [message('user', '<environment_context>\n  <cwd>/synthetic</cwd>\n</environment_context>'),
              message('user', user), {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': user}},
              message('user', '<skill>\n注入技能说明-不应上传\n</skill>'),
              {'type': 'response_item', 'payload': {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': '思考摘要-不应上传'}]}},
              message('assistant', '过程说明-不应上传', phase='commentary'),
              {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'shell', 'arguments': '{}', 'call_id': 'c-' + turn_id}},
              {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'c-' + turn_id, 'output': '工具输出-不应上传'}},
              message('assistant', reply, phase='final_answer'),
              {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': turn_id, 'last_agent_message': reply}}]
    append(path, *items)


def log_path(root, ident):
    return Path(root) / 'home/.codex/sessions/2026/10/29' / f'rollout-2026-10-29T22-00-00-{ident}.jsonl'


def stage(root):
    root = Path(root)
    src = root / 'src'
    if not src.exists():
        ignore = shutil.ignore_patterns('.env', '.env.*', '__pycache__', '*.sqlite3*')
        for part in ('app', 'static', 'plugins', 'scripts'):
            shutil.copytree(REPO / part, src / part, ignore=ignore)
    if (src / '.env').exists():
        raise SystemExit('mirror must not contain .env')
    for ident, label in ((SESSION_A, '合成项目A'), (SESSION_B, '合成项目B')):
        log = log_path(root, ident)
        if not log.exists():
            log.parent.mkdir(parents=True, exist_ok=True)
            # >64KB first line, like real session_meta with embedded base instructions.
            append(log, {'type': 'session_meta', 'payload': {'id': ident, 'cwd': '/synthetic/' + label, 'timestamp': '2026-10-29T14:00:00Z',
                                                              'base_instructions': {'text': '合成说明' * 20000}}})
            codex_turn(log, 'history-1', '连接前的旧历史-' + label, '旧回复-不应上传')
    fixture = root / 'fixture.json'
    if not fixture.exists():
        fixture.write_text(json.dumps([{'id': i, 'name': n, 'phone': p, 'password': 'synthetic-' + secrets.token_hex(8),
                                        'token': secrets.token_urlsafe(24)} for i, n, p in MEMBERS], ensure_ascii=False))
        fixture.chmod(0o600)
    return root


def serve(root, port):
    root = Path(root)
    if (REPO / '.env').exists():
        raise SystemExit('serve only from the staged mirror (no .env)')
    sys.path.insert(0, str(REPO))
    from app.main import create_app, digest, now
    from app.studio import hash_password
    import uvicorn

    def no_model(_context):
        (root / 'model-called').write_text('1')
        raise RuntimeError('CORE-01 must not call any model')
    db = root / 'acceptance.sqlite3'
    app = create_app(db, core_only=True, core_model_runner=no_model)
    with closing(sqlite3.connect(db)) as con:
        for m in json.loads((root / 'fixture.json').read_text()):
            con.execute('INSERT OR IGNORE INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',
                        (m['id'], m['phone'], m['name'], 'CORE-01合成验收', '', digest(m['token']), now(), hash_password(m['password'])))
        con.commit()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


def free_port():
    with closing(socket.socket()) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, root, n):
        self.root, self.port = Path(root), free_port()
        env = {'HOME': str(self.root / 'home'), 'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.log = (self.root / f'server-{n}.log').open('wb')
        script = self.root / 'src/scripts/continuous_sync_acceptance.py'
        self.proc = subprocess.Popen([sys.executable, str(script), 'serve', '--dir', str(self.root), '--port', str(self.port)],
                                     cwd=self.root / 'src', env=env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(100):
            if self.proc.poll() is not None:
                raise SystemExit('isolated server exited; see ' + str(self.root / f'server-{n}.log'))
            try:
                if self.call('GET', '/health')[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        raise SystemExit('isolated server did not start')

    def call(self, method, path, token=None, body=None, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {}), **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read().decode()
                status = r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read().decode(), e.code
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()


def check(root, evidence_path):
    root = stage(root)
    fx = {m['id']: m for m in json.loads((root / 'fixture.json').read_text())}
    ta, tb, tc = fx['core01-a']['token'], fx['core01-b']['token'], fx['core01-c']['token']
    log_a, log_b = log_path(root, SESSION_A), log_path(root, SESSION_B)
    db = root / 'acceptance.sqlite3'
    ev = {'date': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'scope': '隔离TCP服务、临时数据库、临时HOME合成Codex日志；未连接8886、未读取.env、未调用模型',
          'steps': []}

    def step(name, ok, **detail):
        ev['steps'].append({'name': name, 'ok': bool(ok), **detail})
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)
        if not ok:
            raise AssertionError(name + ' ' + json.dumps(detail, ensure_ascii=False))

    def wait(fn, timeout=12):
        end = time.time() + timeout
        while time.time() < end:
            v = fn()
            if v:
                return v
            time.sleep(0.3)
        return fn()

    servers = [Server(root, 1)]
    s = servers[0]
    try:
        base = lambda sid: '/api/core/teams/' + sid
        st, team = s.call('POST', '/api/core/teams', ta, {'name': 'CORE-01合成团队X'})
        sid = team['id']
        s.call('POST', '/api/core/join', tb, {'code': team['code']})
        sid_y = s.call('POST', '/api/core/teams', tc, {'name': 'CORE-01另一团队Y'})[1]['id']
        lib = lambda token=tb, team_id=sid: s.call('GET', base(team_id) + '/library', token)
        ev['port_1'] = s.port

        st, listing = s.call('GET', '/api/core/continuous-sessions', ta)
        ids = [x['id'] for x in listing['items']] if st == 200 else []
        text = json.dumps(listing, ensure_ascii=False)
        step('会话列表只含元数据且能读出>64KB首行的会话', st == 200 and {SESSION_A, SESSION_B} <= set(ids)
             and '旧历史' not in text and '合成说明' not in text and '_path' not in text, status=st, ids=ids)
        st, status = s.call('GET', base(sid) + '/continuous-sync', ta)
        step('新进程初始状态为未连接', st == 200 and status['status'] == 'disconnected', status=status)

        connector = s.call('POST', base(sid) + '/connections', ta, {'label': '手动插件连接'})[1]['token']
        denied = {
            '缺少授权consent': s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A})[0],
            'consent非true': s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': 'yes'})[0],
            '未登录列会话': s.call('GET', '/api/core/continuous-sessions')[0],
            '未登录开启': s.call('POST', base(sid) + '/continuous-sync', None, {'thread_id': SESSION_A, 'consent': True})[0],
            '非本机Host': s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True}, {'Host': 'songban.example.com'})[0],
            '经代理转发': s.call('GET', '/api/core/continuous-sessions', ta, None, {'X-Forwarded-For': '203.0.113.9'})[0],
            '跨站来源': s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True}, {'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'})[0],
            '连接令牌冒充网页登录-列表': s.call('GET', '/api/core/continuous-sessions', connector)[0],
            '连接令牌冒充网页登录-开启': s.call('POST', base(sid) + '/continuous-sync', connector, {'thread_id': SESSION_A, 'consent': True})[0],
            '另队账号开启本队': s.call('POST', base(sid) + '/continuous-sync', tc, {'thread_id': SESSION_A, 'consent': True})[0],
            '另队账号读本队状态': s.call('GET', base(sid) + '/continuous-sync', tc)[0],
            '另队账号停本队': s.call('DELETE', base(sid) + '/continuous-sync', tc)[0],
            '任意路径会话': s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': '../../private', 'consent': True})[0],
        }
        expected = {'缺少授权consent': 422, 'consent非true': 422, '未登录列会话': 401, '未登录开启': 401, '非本机Host': 403, '经代理转发': 403,
                    '跨站来源': 403, '连接令牌冒充网页登录-列表': 401, '连接令牌冒充网页登录-开启': 403, '另队账号开启本队': 403,
                    '另队账号读本队状态': 403, '另队账号停本队': 403, '任意路径会话': 404}
        step('缺授权/未登录/非本机/令牌冒充/跨团队均被拒绝', denied == expected, got=denied, expected=expected)
        step('拒绝后仍未连接且资料库为空', s.call('GET', base(sid) + '/continuous-sync', ta)[1]['status'] == 'disconnected' and lib()[1]['items'] == [])

        st, started = s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True})
        step('本机网页登录用户授权后开始持续同步', st == 200 and started['status'] == 'running', status=st)
        time.sleep(2.5)
        step('连接后历史内容不入库', lib()[1]['items'] == [])

        turn1_user = '第一轮：把登录接口接到前端。部署前确认 API_KEY=' + FAKE + ' 不要外泄'
        codex_turn(log_a, 'turn-1', turn1_user, '登录接口已接好。\n要点：前端调用 /login 返回200；Bearer ' + FAKE)
        codex_turn(log_b, 'other-1', '另一个未选择会话的正文-不应上传', '其他会话回复-不应上传')
        items = wait(lambda: (lambda r: r if len(r) >= 1 else None)(lib()[1]['items'])) or []
        st_a = s.call('GET', base(sid) + '/continuous-sync', ta)[1]
        r1 = items[0]['report'] if items else {}
        step('第一回合自动入库，记录号可从library读回', len(items) == 1 and st_a['last_note_id'] == items[0]['id'] and st_a['sent'] == 1,
             note_id=items[0]['id'] if items else None, status=st_a)
        step('注册姓名/原文/要点/实际模型名正确且伪凭据脱敏',
             items[0]['author'] == '甲·合成成员' and r1['user_message'].startswith('第一轮：把登录接口接到前端。') and '[已隐藏]' in r1['user_message']
             and r1['assistant_summary'].startswith('登录接口已接好。') and r1['model_name'] == 'synthetic-model-x1'
             and FAKE not in json.dumps(items, ensure_ascii=False), user_message=r1.get('user_message'), assistant_summary=r1.get('assistant_summary'), model=r1.get('model_name'))

        codex_turn(log_a, 'turn-2', '第二轮：补充错误提示文案。', '已补充三种错误提示。', model='')
        items = wait(lambda: (lambda r: r if len(r) >= 2 else None)(lib()[1]['items'])) or []
        r2 = items[0]['report'] if items else {}
        step('第二回合分别自动入库，未知模型不猜测', len(items) == 2 and r2['user_message'] == '第二轮：补充错误提示文案。' and r2['model_name'] == '',
             model=r2.get('model_name'))
        raw = json.dumps(items, ensure_ascii=False)
        hidden = ['旧历史', '旧回复', 'environment_context', '注入技能', '思考摘要', '过程说明', '工具输出', '另一个未选择会话', '其他会话回复', FAKE]
        step('思考/工具输出/注入内容/旧历史/其他会话均未出现', not [h for h in hidden if h in raw], leaked=[h for h in hidden if h in raw and h != FAKE])
        step('同队第二账号可见', len(lib(tb)[1]['items']) == 2)
        step('另队账号读本队资料库被拒，自己团队为空', lib(tc)[0] == 403 and lib(tc, sid_y)[1]['items'] == [])

        codex_turn(log_a, 'turn-1', turn1_user, '登录接口已接好。\n要点：前端调用 /login 返回200；Bearer ' + FAKE)
        time.sleep(4.5)
        with closing(sqlite3.connect(db)) as con:
            dup = con.execute("SELECT COUNT(*) FROM library_notes WHERE squad_id=? AND body LIKE '%第一轮%'", (sid,)).fetchone()[0]
        step('重复事件只生成一条记录', len(lib()[1]['items']) == 2 and dup == 1, library_rows_for_turn1=dup)

        db.chmod(0o444)  # injected transient write failure
        codex_turn(log_a, 'turn-3', '第三轮：临时失败时写入。', '第三轮回复。')
        failing = wait(lambda: (lambda x: x if x['status'] == 'retrying' else None)(s.call('GET', base(sid) + '/continuous-sync', ta)[1]), 8)
        during = len(lib()[1]['items'])
        # SQLite creates -wal/-shm with the database file's mode, so restore every sibling.
        for p in root.glob('acceptance.sqlite3*'):
            p.chmod(0o644)
        step('临时写入失败显示等待重试而非成功', failing and failing['status'] == 'retrying' and failing['sent'] == 2 and during == 2,
             status=failing)
        items = wait(lambda: (lambda r: r if len(r) >= 3 else None)(lib()[1]['items'])) or []
        time.sleep(2.5)
        items = lib()[1]['items']
        st_a = s.call('GET', base(sid) + '/continuous-sync', ta)[1]
        step('恢复后补传一次且不重复', len(items) == 3 and sum(i['report']['user_message'] == '第三轮：临时失败时写入。' for i in items) == 1
             and st_a['status'] == 'running' and st_a['sent'] == 3, status=st_a)

        st, stopped = s.call('DELETE', base(sid) + '/continuous-sync', ta)
        conns = {c['id']: c for c in s.call('GET', base(sid) + '/connections', ta)[1]['items']}
        step('停止后状态为已停止且连接撤销', st == 200 and stopped['status'] == 'stopped' and conns[stopped['connection_id']]['revoked'] == 1)
        codex_turn(log_a, 'turn-4', '第四轮：停止期间-不应上传', '停止期间回复')
        time.sleep(4.5)
        step('停止后追加回合不入库', len(lib()[1]['items']) == 3)

        st, again = s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True})
        codex_turn(log_a, 'turn-5', '第五轮：重新连接后', '重连后的回复')
        items = wait(lambda: (lambda r: r if len(r) >= 4 else None)(lib()[1]['items'])) or []
        time.sleep(2.5)
        items = lib()[1]['items']
        step('重连不补传停用期间内容，只同步重连后回合', len(items) == 4 and items[0]['report']['user_message'] == '第五轮：重新连接后'
             and '停止期间' not in json.dumps(items, ensure_ascii=False))

        for action in ('pause', 'revoke'):
            cid = s.call('GET', base(sid) + '/continuous-sync', ta)[1]['connection_id']
            s.call('PATCH', base(sid) + '/connections/' + cid, ta, {'action': action})
            now_status = s.call('GET', base(sid) + '/continuous-sync', ta)[1]['status']
            if action == 'pause':
                s.call('PATCH', base(sid) + '/connections/' + cid, ta, {'action': 'resume'})
            codex_turn(log_a, 'turn-' + action, f'{action}后追加-不应上传', '不应上传')
            time.sleep(4.5)
            step(f'在连接列表{"暂停(随后恢复)" if action == "pause" else "撤销"}后立即停止且不上传',
                 now_status == 'stopped' and len(lib()[1]['items']) == 4, status=now_status)
            if action == 'pause':
                s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True})

        st, b_started = s.call('POST', base(sid) + '/continuous-sync', tb, {'thread_id': SESSION_B, 'consent': True})
        codex_turn(log_b, 'b-1', '乙的一轮：整理演示脚本', '演示脚本已分三段。', model='synthetic-model-y2')
        items = wait(lambda: (lambda r: r if len(r) >= 5 else None)(lib()[1]['items'])) or []
        step('第二账号独立连接，姓名由其认证账号确定', st == 200 and len(items) == 5 and items[0]['author'] == '乙·合成成员'
             and items[0]['report']['model_name'] == 'synthetic-model-y2')
        s.call('DELETE', base(sid) + '/continuous-sync', tb)

        st, live = s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True})
        live_cid = live['connection_id']
        s.stop()
        with closing(sqlite3.connect(db)) as con:
            revoked = con.execute('SELECT revoked FROM core_connections WHERE id=?', (live_cid,)).fetchone()[0]
        step('服务正常关闭时撤销进行中的持续同步连接', revoked == 1)
        codex_turn(log_a, 'turn-offline', '服务停止期间-不应上传', '不应上传')
        s = Server(root, 2)
        servers.append(s)
        ev['port_2'] = s.port
        st_new = s.call('GET', base(sid) + '/continuous-sync', ta)[1]
        codex_turn(log_a, 'turn-restart', '重启后未重连-不应上传', '不应上传')
        time.sleep(4.5)
        items = lib()[1]['items']
        step('启动新隔离进程后状态为未连接，不偷偷恢复采集', st_new['status'] == 'disconnected' and len(items) == 5
             and '不应上传' not in json.dumps(items, ensure_ascii=False), status=st_new)

        s.call('POST', base(sid) + '/continuous-sync', ta, {'thread_id': SESSION_A, 'consent': True})
        with closing(sqlite3.connect(db)) as con:
            con.execute('DELETE FROM squad_members WHERE squad_id=? AND user_id=?', (sid, 'core01-a'))
            con.commit()
        codex_turn(log_a, 'turn-left', '退出团队后-不应上传', '不应上传')
        time.sleep(4.5)
        step('成员被移出团队后不再上传（核心版无退出入口，直接在隔离库删除成员关系模拟）',
             len(lib()[1]['items']) == 5 and s.call('GET', base(sid) + '/continuous-sync', ta)[0] == 403)

        snap = s.call('GET', base(sid), tb)[1]
        step('只记录不分析：无草案、未调用模型', not snap.get('proposal') and not (root / 'model-called').exists())
        items = lib()[1]['items']
        ev['library_two_lines'] = [[f"{i['author']}：{i['report']['user_message']}", f"{i['report']['model_name'] or '模型名未获取'}：{i['report']['assistant_summary']}"] for i in items]
        logs = b''.join((root / f'server-{n}.log').read_bytes() for n in (1, 2))
        step('服务日志不含伪凭据', FAKE.encode() not in logs)
    finally:
        for server in servers:
            server.stop()
    out = json.dumps(ev, ensure_ascii=False, indent=2)
    if FAKE in out:
        raise AssertionError('evidence must not contain the synthetic credential')
    Path(evidence_path).parent.mkdir(parents=True, exist_ok=True)
    Path(evidence_path).write_text(out + '\n')
    print('全部通过；证据写入', evidence_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', default='check', choices=('check', 'stage', 'serve'))
    parser.add_argument('--dir')
    parser.add_argument('--port', type=int)
    parser.add_argument('--keep', action='store_true')
    parser.add_argument('--evidence', default=str(REPO / 'docs/reviews/core-01-evidence/tcp_acceptance.json'))
    args = parser.parse_args()
    if args.mode == 'stage':
        print(stage(args.dir))
    elif args.mode == 'serve':
        serve(args.dir, args.port)
    else:
        root = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix='songban-core01-'))
        try:
            check(root, args.evidence)
        finally:
            if not args.keep and not args.dir:
                shutil.rmtree(root, ignore_errors=True)
