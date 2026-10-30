"""Loopback QA only: real SQLite/API, simulated SMS and explicit model fixture."""
import sys
from pathlib import Path
from unittest.mock import patch

checkout = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(checkout))
from app.main import create_app
from tests.test_team_core import plan_for
import uvicorn

if __name__ == '__main__':
    with patch('app.studio.must_deliver', return_value=False), \
         patch('app.studio.test_codes_allowed', return_value=True), \
         patch('app.studio.deliver_login_code', return_value=(False, '本机开发测试，不发送短信')), \
         patch('app.team_core.team_model_config', return_value={'api_key':'', 'model_id':'协议测试'}):
        app = create_app(checkout / '.browser-cache' / 'unified-qa.sqlite3', core_only=True, core_model_runner=plan_for)
        uvicorn.run(app, host='127.0.0.1', port=8892, log_level='warning')
