"""Read this project's private UTF-8 configuration without starting the application."""
import os
from pathlib import Path

from .email_delivery import EMAIL_KEYS


ROOT = Path(__file__).resolve().parents[1]
SMS_KEYS = frozenset({
    'ALIYUN_ACCESS_KEY_ID', 'ALIYUN_ACCESS_KEY_SECRET', 'ALIYUN_SMS_SIGN_NAME',
    'ALIYUN_SMS_TEMPLATE_CODE', 'ALIYUN_SMS_MODE', 'SONGBAI_REQUIRE_SMS',
    'SONGBAI_ALLOW_TEST_CODES', 'SONGBAI_IMESSAGE', 'SONGBAI_SMS',
})
ENV_KEYS = SMS_KEYS | EMAIL_KEYS | {
    'DEEPSEEK_API_KEY', 'MODEL_API_KEY', 'MODEL_BASE_URL', 'MODEL_NAME',
    'TEAM_MODEL_API_KEY', 'TEAM_MODEL_BASE_URL', 'TEAM_MODEL_NAME',
    'DASHSCOPE_API_KEY', 'MODEL_ALLOWED_HOSTS', 'ALLOWED_ORIGINS',
    'SONGBAN_CORE_ONLY', 'DATABASE_PATH', 'PUBLIC_BASE_URL',
    'WECHAT_APP_ID', 'WECHAT_APP_SECRET',
}


def load_env(path=None, *, keys=ENV_KEYS):
    path = Path(path) if path is not None else ROOT / '.env'
    if not path.exists():
        return
    # Windows editors may write a BOM; Chinese SMS signatures must stay UTF-8.
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        key = name.strip()
        if key not in keys:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        # Nonempty project values win; blank template entries do not erase
        # injected deployment settings (the application's existing precedence).
        if value:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, '')
