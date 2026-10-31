"""Check SMS configuration without sending messages or printing private values."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.environment import load_env, SMS_KEYS
from app.sms import _signed_get, provider_failure, sms_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Private UTF-8 file; defaults to the project .env, never prints values')
    parser.add_argument('--check-identity', action='store_true', help='Read-only Aliyun STS request; does not send SMS')
    args = parser.parse_args()
    if args.env_file and not args.env_file.is_file():
        parser.error('指定的配置文件不存在；请提供本机私密 .env 的路径。')
    try:
        load_env(args.env_file, keys=SMS_KEYS)
    except (OSError, UnicodeError):
        parser.error('无法读取配置文件；请检查权限并保存为 UTF-8。')
    status = sms_status()
    result = {k: status[k] for k in ('configured', 'provider', 'missing', 'delivery_verified')}
    result['test_codes_disabled'] = os.environ.get('SONGBAI_ALLOW_TEST_CODES') != '1'
    if args.check_identity and result['configured']:
        body = _signed_get('sts.aliyuncs.com', '2015-04-01', {'Action': 'GetCallerIdentity'})
        result['identity_verified'] = bool(body and body.get('AccountId'))
        if not result['identity_verified']:
            result['notice'] = provider_failure(body)
    result['notice'] = result.get('notice', '仅检查配置和可选身份认证；未验证短信权限、余额或实际送达。')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['configured'] and result['test_codes_disabled'] and result.get('identity_verified', True) else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
