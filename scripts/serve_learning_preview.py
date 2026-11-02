"""Run the real app against an explicitly marked, synthetic-only local database.

No private .env, existing database, real provider, email, or SMS is used. This is
an engineering preview, not a production launch or real guardian approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCOPE = 'synthetic-only-no-real-providers'
MARKER = '.songban-learning-preview.json'
DATABASE = 'synthetic-learning.sqlite3'
METADATA = 'preview-metadata.json'
PASSWORD = 'studio-synthetic-only-password'
ACTORS = (
    ('preview-parent-a', 'family-preview', '18800000971', '虚构家长甲'),
    ('preview-parent-b', 'other-preview', '18800000972', '虚构家长乙'),
    ('preview-reviewer', 'reviewer-preview', '18800000973', '虚构复核员'),
)


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _verify_synthetic_database(path, *, import_only=False):
    if not path.exists():
        return
    if path.is_symlink() or not path.is_file():
        raise ValueError('Preview database must be a regular file in its dedicated directory')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='people'").fetchone():
            raise ValueError('Existing preview database has no synthetic identity schema')
        actors = {r[0] for r in con.execute('SELECT id FROM people')}
        expected = set() if import_only else {a[0] for a in ACTORS}
        if not actors <= expected:
            raise ValueError('Refusing a database containing identities outside this synthetic fixture')


def prepare_directory(directory):
    path = Path(directory).expanduser().resolve()
    if path == Path(path.anchor) or path == ROOT or path in ROOT.parents or ROOT in path.parents:
        raise ValueError('Use a separate output directory outside the repository, never its data directory')
    if path.exists() and (not path.is_dir() or path.is_symlink()):
        raise ValueError('Preview output must be a regular directory')
    if path.exists() and any(path.iterdir()):
        marker_path = path / MARKER
        if not marker_path.is_file() or marker_path.is_symlink():
            raise ValueError('Nonempty directory has no preview marker; use a fresh dedicated directory')
        marker = _read_json(marker_path)
        if marker.get('scope') != SCOPE or marker.get('version') != 1 or marker.get('database') != DATABASE:
            raise ValueError('Preview marker does not match this synthetic fixture')
        if marker.get('ready') is not True or not (path / METADATA).is_file():
            raise ValueError('Incomplete preview setup; use a fresh directory without deleting previous evidence')
        allowed = {DATABASE, DATABASE+'-wal', DATABASE+'-shm', 'import-only.sqlite3',
                   'import-only.sqlite3-wal', 'import-only.sqlite3-shm'}
        if any(p.name not in allowed for p in path.glob('*.sqlite3*')):
            raise ValueError('Unexpected database in preview directory')
        _verify_synthetic_database(path / DATABASE)
        _verify_synthetic_database(path / 'import-only.sqlite3', import_only=True)
        metadata = _read_json(path / METADATA)
        if metadata.get('synthetic') is not True or metadata.get('scope') != SCOPE or Path(metadata['database']).resolve() != path / DATABASE:
            raise ValueError('Preview metadata is not bound to this synthetic database')
        return path, False
    path.mkdir(parents=True, exist_ok=True)
    _write_json(path / MARKER, {'version': 1, 'scope': SCOPE, 'database': DATABASE, 'ready': False})
    return path, True


def _isolate_environment(directory):
    from app.environment import ENV_KEYS
    # Only this dedicated preview process is modified. Never print removed values.
    for key in tuple(os.environ):
        if key in ENV_KEYS or key.startswith(('SONGBAN_', 'SONGBAI_', 'SMTP_', 'ALIYUN_', 'DEEPSEEK_', 'DASHSCOPE_')):
            os.environ.pop(key, None)
    os.environ.update(DATABASE_PATH=str(directory / 'import-only.sqlite3'),
                      SONGBAN_CORE_ONLY='1', SONGBAN_ENFORCE_JOURNEY='0')


def _settings(origin):
    from app.learning_v2 import ReviewQueue, Settings
    queue = ReviewQueue('preview-reviewer', '虚构复核员', 3600, '隔离测试：使用 reviewer-preview 账号处理')
    return Settings(enabled=True, navigation_enabled=True, studio_enabled=True, catalog_enabled=True,
                    course_enabled=True, mock_enabled=True, models_enabled=True, model_settings=None,
                    reports_enabled=True, publication_enabled=True, allowed_origins=(origin,), loopback_http=True,
                    consent_version='studio-fiction-v1', age_band_options=('6–8岁', '9–12岁', '13–17岁'),
                    relationship_queue=queue, learning_queue=queue, support_queue=queue, report_queue=queue)


def _seed_identities(service, database):
    from app.studio import hash_password
    timestamp = service.stamp()
    with closing(sqlite3.connect(database)) as con:
        existing = {r[0] for r in con.execute('SELECT id FROM people')}
        if existing:
            raise ValueError('Fresh fixture unexpectedly already contains people')
        for actor, account, phone, label in ACTORS:
            con.execute('INSERT INTO people(id,phone,name,token_hash,created_at,password_hash,username) VALUES(?,?,?,?,?,?,?)',
                        (actor, phone, label, hashlib.sha256(('preview-unused-'+uuid.uuid4().hex).encode()).hexdigest(),
                         timestamp, hash_password(PASSWORD), account))
        con.commit()
    for scope in ('relationship_review', 'consent_read', 'learning_review', 'support', 'report_review', 'report_publish'):
        service.grant_staff('preview-reviewer', scope, service.clock()+7*86400, authority=SCOPE)
    content = {'locale': 'zh-CN', 'title': '仅限虚构工程预览的授权',
               'text': '所有账号、关系、活动及作品均为虚构测试资料，不代表真实监护人同意或真实教学结论。',
               'scope_purposes': [{'scope': 'learning', 'purpose': '虚构首课流程测试'},
                                  {'scope': 'parent_summary', 'purpose': '虚构家长摘要测试'},
                                  {'scope': 'report_publication', 'purpose': '仅发布虚构报告'}]}
    service.put_consent_text({'consent_version': 'studio-fiction-v1', **content,
                             'text_sha256': hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
                             'approval_status': 'approved_for_pilot', 'approved_at': timestamp,
                             'acceptance_enabled': True, 'notice': '合成数据专用，不可作为真实授权文本'}, authority=SCOPE)


def _provision(api, origin):
    from fastapi.testclient import TestClient
    service = api.state.learning_v2
    course = service.provision_invitation_course(authority=SCOPE)
    # Preparation uses in-process HTTP only. Do not start two lifespans/event
    # loops for the same app-owned worker; uvicorn starts it once when serving.
    with closing(TestClient(api, base_url=origin)) as parent, closing(TestClient(api, base_url=origin)) as reviewer:
        def get(client, path):
            response = client.get('/api/learning/v2'+path)
            if not response.is_success:
                raise RuntimeError('Synthetic preparation failed: GET '+path+' '+str(response.status_code))
            return response.json()

        def post(client, path, body):
            boot = get(client, '/session-bootstrap')
            response = client.post('/api/learning/v2'+path, json={'request_id': uuid.uuid4().hex, **body},
                                   headers={'Origin': origin, 'X-CSRF-Token': boot['csrf_token']})
            if not response.is_success:
                raise RuntimeError('Synthetic preparation failed: POST '+path+' '+str(response.status_code))
            return response.json()

        def login(client, account):
            boot = get(client, '/session-bootstrap')
            post(client, '/sessions/authenticate', {'browser_revision': boot['browser_revision'],
                                                  'method': 'password', 'account': account, 'proof': PASSWORD})

        login(parent, 'family-preview')
        family = post(parent, '/families', {})
        learner = post(parent, '/families/'+family['id']+'/learners', {
            'expected_revision': family['revision'], 'display_name': '小松同学（虚构）', 'age_band': '9–12岁',
            'declared_relationship': '虚构工程预览的监护人声明'})
        login(reviewer, 'reviewer-preview')
        case = next(c for c in get(reviewer, '/cases')['items'] if c['learner_id'] == learner['id'])
        evidence = service.add_relationship_evidence(case['id'], '仅用于合成身份演练的核对依据；没有真实儿童资料。', authority=SCOPE)
        claimed = post(reviewer, '/cases/'+case['id']+'/claim', {'expected_revision': case['revision']})
        post(reviewer, '/cases/'+case['id']+'/resolve', {'expected_revision': claimed['revision'],
             'target_revision': learner['revision'], 'decision': 'verified', 'evidence_ids': [evidence],
             'note': '虚构家庭关系经隔离测试流程确认', 'manual_findings': []})
        profile = get(parent, '/learners/'+learner['id']+'/profile')
        post(parent, '/learners/'+learner['id']+'/consents', {'expected_revision': profile['revision'],
             'consent_version': 'studio-fiction-v1', 'scopes': ['learning', 'parent_summary', 'report_publication'], 'acknowledged': True})
        entitlement = service.grant_course_access(learner['id'], course, service.clock()+7*86400, authority=SCOPE)
        profile = get(parent, '/learners/'+learner['id']+'/profile')
        enrollment = post(parent, '/learners/'+learner['id']+'/enrollments', {
            'expected_revision': profile['revision'], 'course_version_id': course, 'entitlement_id': entitlement})
    return {'learner_id': learner['id'], 'family_id': family['id'], 'course_id': course,
            'enrollment_id': enrollment['id'], 'relationship_case_id': case['id']}


def _seed_interview(service):
    from app.interview import LIST_FIELDS
    draft = {key: [] for key in LIST_FIELDS}
    item = lambda text: {'text': text, 'basis': 'self_reported', 'evidence': ['preview-user-1']}
    draft.update(goals=[item('做一张故事交换会邀请卡')], experiences=[item('和朋友试着修改过一次邀请文字')],
                 time_available=None, conflicts=[], unknowns=['帮助偏好尚未了解'])
    meta = {'missing_fields': ['time_available', 'help_needed'], 'reason': 'synthetic_fixture', 'model': None}
    stamp = service.stamp()
    with service.store.transaction() as con:
        con.execute('INSERT INTO core_interviews(user_id,age_band,stage,status,version,draft,draft_meta,source,confirmed_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    ('preview-parent-a', 'under_13', 'primary_school', 'confirmed', 1,
                     json.dumps(draft, ensure_ascii=False), json.dumps(meta, ensure_ascii=False),
                     json.dumps({'kind': 'synthetic_fixture', 'notice': '虚构儿童访谈，待管理者明确关联孩子'}), stamp, stamp, stamp))
        con.execute('INSERT INTO core_interview_messages(user_id,seq,id,role,text,created_at) VALUES(?,?,?,?,?,?)',
                    ('preview-parent-a', 1, 'preview-user-1', 'user', '我想做故事交换会邀请卡，和朋友试着改过一次邀请文字。', stamp))


def build_preview(directory, port=8897):
    if not 1024 <= port <= 65535 or port in (8893, 8894, 8895, 8896):
        raise ValueError('Use a dedicated unprivileged preview port (default 8897), not an existing app port')
    directory, fresh = prepare_directory(directory)
    _isolate_environment(directory)
    # app.main has a legacy module-level create_app(). Its temporary import DB is
    # explicitly redirected inside the marked directory before importing it.
    with patch('app.environment.load_env'):
        from app.main import create_app
    origin = f'http://127.0.0.1:{port}'
    api = create_app(db_path=directory / DATABASE, core_only=True, enforce_journey=False, learning_settings=_settings(origin))
    if fresh:
        _seed_identities(api.state.learning_v2, directory / DATABASE)
        entities = _provision(api, origin)
        _seed_interview(api.state.learning_v2)
        metadata = {'synthetic': True, 'scope': SCOPE, **entities, 'database': str(directory / DATABASE),
                    'manager_account': 'family-preview', 'other_account': 'other-preview',
                    'staff_account': 'reviewer-preview', 'password': PASSWORD,
                    'prepared': {'relationship': True, 'learning_consent': True, 'course_enrollment': True},
                    'initial_run': 'not_created', 'real_provider_calls': 0}
    else:
        metadata = _read_json(directory / METADATA)
    metadata.update(origin=origin, learning_url=origin+'/learning-prep#/learn/first',
                    manager_url=origin+'/learning-prep#/family', mode='static-and-mock-only',
                    notice='所有身份与活动均为虚构。未预填作品、检查或过关；报告需要实际走完流程。')
    _write_json(directory / METADATA, metadata)
    _write_json(directory / MARKER, {'version': 1, 'scope': SCOPE, 'database': DATABASE, 'ready': True})
    return api, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8897)
    parser.add_argument('--directory', type=Path, default=ROOT.parent/'outputs'/('learning-studio-preview-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]))
    args = parser.parse_args()
    api, metadata = build_preview(args.directory, args.port)
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)
    import uvicorn
    uvicorn.run(api, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
