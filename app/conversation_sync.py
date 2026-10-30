"""Opt-in local Codex transcript tailer. Never imports historical turns or reasoning."""
import hashlib
import json
from pathlib import Path
import re
import threading


class SyncError(ValueError):
    pass


def session_root():
    return Path.home() / '.codex/sessions'


def sessions(root=None):
    """Read only session metadata, not message previews. Paths never leave this module."""
    root = Path(root) if root is not None else session_root()
    if not root.is_dir():
        return []
    files = sorted(root.rglob('rollout-*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)[:300]
    result, seen = [], set()
    for path in files:
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                continue
            with path.open('rb') as f:
                # Real session_meta lines embed base instructions and can exceed 64KB.
                row = json.loads(f.readline(2_000_000))
            meta = row.get('payload', {})
            ident = meta.get('id', '')
            if row.get('type') != 'session_meta' or not re.fullmatch(r'[a-zA-Z0-9-]{8,100}', ident) or ident in seen:
                continue
            seen.add(ident)
            result.append({'id': ident, 'cwd': str(meta.get('cwd', ''))[:1000],
                           'started_at': str(meta.get('timestamp', ''))[:80], '_path': path})
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return result[:30]


def key_reply(text):
    # Explicit extractive summary, no extra model call or analysis.
    text = text.strip()
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.startswith('```')]
    return '\n'.join(lines)[:800]


# Codex records its own context injections as user-role items; they are not the user's words.
INJECTED = ('<environment_context', '<user_instructions', '# AGENTS.md instructions', '<skill',
            '<turn_aborted', '<subagent_notification', '<user_shell_command', '<permissions')
FINAL_PHASES = ('final', 'final_answer')


class Reader:
    def __init__(self, path, ident):
        self.path, self.ident = Path(path), ident
        stat = self.path.stat()
        self.inode, self.offset = stat.st_ino, stat.st_size  # Never backfill history.
        self.user = self.reply = self.model = self.turn = ''
        self.typed = False
        self.seen = set()

    def poll(self):
        stat = self.path.stat()
        if stat.st_ino != self.inode or stat.st_size < self.offset:
            raise SyncError('对话文件已替换或截断，请重新选择连接；未补传历史。')
        results = []
        with self.path.open('rb') as f:
            f.seek(self.offset)
            for _ in range(300):
                line = f.readline(2_000_001)
                if not line:
                    break
                if len(line) > 2_000_000:
                    raise SyncError('对话日志单条过大，已停止；请检查后重新连接。')
                if not line.endswith(b'\n'):
                    break  # Incomplete append: retry the same offset.
                self.offset = f.tell()
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    raise SyncError('对话日志格式异常，已停止同步。') from None
                event = self.consume(item)
                if event:
                    results.append(event)
        return results

    def consume(self, item):
        p = item.get('payload', {})
        if not isinstance(p, dict):
            return
        kind, typ = item.get('type'), p.get('type')
        if kind == 'turn_context':
            self.model = str(p.get('model') or '')[:160]
        elif kind == 'event_msg' and typ == 'task_started':
            self.turn = str(p.get('turn_id') or p.get('root_turn_id') or '')
        elif kind == 'event_msg' and typ == 'user_message':
            text = p.get('message')
            if isinstance(text, str) and text.strip():
                self.user, self.reply, self.typed = text, '', True
        elif kind == 'response_item' and typ == 'message':
            role = p.get('role')
            # Never inspect tool results, encrypted reasoning or analysis/commentary.
            if role not in ('user', 'assistant'):
                return
            if role == 'assistant' and p.get('phase') not in FINAL_PHASES:
                return
            text = '\n'.join(c.get('text', '') for c in p.get('content', [])
                             if isinstance(c, dict) and c.get('type') in ('input_text', 'output_text'))
            if role == 'user':
                if text.strip() and not self.typed and not text.lstrip().startswith(INJECTED):
                    self.user = text
                    self.reply = ''
            else:
                self.reply = text
        elif kind == 'event_msg' and typ in ('turn_aborted', 'task_aborted'):
            self.user = self.reply = ''
            self.typed = False
        elif kind == 'event_msg' and typ == 'task_complete':
            turn = str(p.get('turn_id') or self.turn)
            reply = self.reply or p.get('last_agent_message', '')
            self.typed = False
            if not self.user or not isinstance(reply, str) or not reply.strip():
                self.user = self.reply = ''
                return
            if len(self.user) > 16000:
                raise SyncError('本轮用户文字超过16000字，已停止，未静默截断上传。')
            event = {'selected': True, 'event_id': 'continuous-' + hashlib.sha256(
                (self.ident + ':' + (turn or str(self.offset))).encode()).hexdigest(),
                'user_message': self.user, 'assistant_summary': key_reply(reply),
                'model_name': self.model, 'session_label': 'Codex持续同步 · ' + self.ident[:8]}
            self.user = self.reply = self.model = ''
            if event['event_id'] not in self.seen:
                self.seen.add(event['event_id'])
                return event


class Manager:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.RLock()

    def start(self, key, reader, send, check, connection_id, background=True):
        self.stop(key)
        job = {'reader': reader, 'send': send, 'check': check, 'stop': threading.Event(),
               'connection_id': connection_id, 'thread_id': reader.ident, 'status': 'running',
               'sent': 0, 'pending': [], 'error': '', 'last_note_id': ''}
        with self.lock:
            self.jobs[key] = job
        if background:
            threading.Thread(target=self.run, args=(job,), daemon=True).start()
        return self.status(key)

    def tick(self, job):
        # The same lock serializes stop and upload, so no upload can begin after stop returns.
        with self.lock:
            if job['stop'].is_set():
                return
            try:
                job['check']()  # Recheck team membership, connection pause/revoke before reading.
            except Exception as e:
                if getattr(e, 'status', None) in (401, 403):
                    job.update(status='stopped', error='连接已暂停、撤销、过期或成员权限已变化；请重新连接。')
                    job['pending'].clear()
                    job['stop'].set()
                else:
                    job.update(status='retrying', error='暂时无法核对连接，稍后重试；请勿当作已同步。')
                return
            try:
                if not job['pending']:
                    job['pending'].extend(job['reader'].poll())
                while job['pending']:
                    receipt = job['send'](job['pending'][0])
                    if not receipt.get('note_id'):
                        raise SyncError('服务器未返回记录号，未确认上传。')
                    job.update(sent=job['sent'] + 1, last_note_id=receipt['note_id'], error='', status='running')
                    job['pending'].pop(0)
            except (SyncError, OSError):
                job.update(status='stopped', error='对话日志读取异常，已停止；请重新选择连接。')
                job['stop'].set()
            except Exception as e:
                status = getattr(e, 'status', None)
                if status in (401, 403):
                    job.update(status='stopped', error='连接已暂停、撤销、过期或成员权限已变化；请重新连接。')
                    job['pending'].clear()
                    job['stop'].set()
                elif status and 400 <= status < 500 and status != 429:
                    # Retrying a rejected payload can never succeed; stop visibly instead of looping.
                    job.update(status='stopped', error='本轮内容未被资料库接受，已停止；未上传，请检查后重新连接。')
                    job['pending'].clear()
                    job['stop'].set()
                else:
                    # Keep the same event id and payload until acknowledged; no model calls.
                    job.update(status='retrying', error='本轮尚未确认上传，稍后重试；请勿当作已同步。')

    def run(self, job):
        while not job['stop'].wait(2):
            self.tick(job)

    def stop(self, key):
        with self.lock:
            job = self.jobs.get(key)
            if job:
                job['stop'].set()
                job['pending'].clear()
                job['status'] = 'stopped'
        return self.status(key)

    def status(self, key):
        with self.lock:
            job = self.jobs.get(key)
            return ({k: job[k] for k in ('thread_id', 'connection_id', 'status', 'sent', 'error', 'last_note_id')}
                    if job else {'status': 'disconnected', 'sent': 0, 'error': ''})

    def close(self):
        """Stop every job; returns (key, connection_id) pairs so callers can revoke the bindings."""
        stopped = []
        for key in list(self.jobs):
            stopped.append((key, self.stop(key).get('connection_id')))
        return stopped
