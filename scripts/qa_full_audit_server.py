"""Isolated local audit server; synthetic accounts and explicit SMS/model fixtures."""
import json
import os
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import create_app, digest, now
from app.studio import hash_password
from tests.test_team_core import plan_for
from tests.test_materials import fixture_model
from scripts.qa_materials_server import fixtures
from fastapi.testclient import TestClient
import uvicorn


def main():
    folder = ROOT / '.browser-cache/materials/full-audit-20261031'
    folder.mkdir(parents=True, exist_ok=True)
    db = folder / ('browser-' + uuid.uuid4().hex[:8] + '.sqlite3')
    port = int(os.environ.get('SONGBAN_AUDIT_PORT', '8894'))
    fixtures(ROOT / '.browser-cache/materials')
    with patch('app.studio.must_deliver', return_value=False), patch('app.studio.test_codes_allowed', return_value=True), patch('app.studio.deliver_login_code', return_value=(False, '本机隔离测试，无短信发送')):
        app = create_app(db, core_only=True, core_model_runner=plan_for, materials_model_runner=fixture_model)

        @app.get('/api/audit-fixture')
        def audit_marker():
            return {'isolated_audit': True, 'sms': 'fixture', 'model': 'fixture'}

        with closing(sqlite3.connect(db)) as con:
            for ident, phone, name in [('qa-materials', '18800008893', '资料测试同伴'), ('qa-materials-b', '18800008894', '资料测试队友')]:
                con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)', (ident, phone, name, '合成测试', '测试', digest('test-' + ident), now(), hash_password('materials-test-password')))
            con.commit()
        with TestClient(app) as client:
            team = client.post('/api/core/teams', headers={'Authorization': 'Bearer test-qa-materials'}, json={'name': '全量审核测试小队'}).json()
            client.post('/api/core/join', headers={'Authorization': 'Bearer test-qa-materials-b'}, json={'code': team['code']})
        (folder / 'browser-server.json').write_text(json.dumps({'database': str(db), 'port': port, 'sms': 'fixture', 'model': 'fixture'}), encoding='utf-8')
        uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


if __name__ == '__main__':
    main()
