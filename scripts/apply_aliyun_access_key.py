#!/usr/bin/env python3
"""Configure local SMS interactively; never retrieves GitHub secrets or sends SMS."""
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.environment import load_env, SMS_KEYS
from app.private_files import restrict_file
from app.sms import sms_status

REQUIRED_KEYS = ('ALIYUN_ACCESS_KEY_ID', 'ALIYUN_ACCESS_KEY_SECRET',
                 'ALIYUN_SMS_SIGN_NAME', 'ALIYUN_SMS_TEMPLATE_CODE')


def write_sms_config(path, values, mode='pnvs'):
    """Write only supplied SMS settings; preserve other application settings."""
    if mode not in {'pnvs', 'enterprise'}:
        raise ValueError('短信模式必须为 pnvs 或 enterprise。')
    settings = {key: str(values.get(key, '')).strip() for key in REQUIRED_KEYS}
    for key, value in settings.items():
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(f'{key} 必须填写完整的单行值；没有写入配置。')
    settings.update(ALIYUN_SMS_MODE=mode, SONGBAI_REQUIRE_SMS='1',
                    SONGBAI_ALLOW_TEST_CODES='0', SONGBAI_IMESSAGE='0', SONGBAI_SMS='0')
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig') if path.exists() else '# 松伴本机私密配置；不要提交或分享。\n'
    for key, value in settings.items():
        # The parser removes one quote pair, preserving literal quotes and slashes.
        line = f'{key}="{value}"'
        pattern = re.compile(rf'^[ \t]*{re.escape(key)}[ \t]*=.*$', re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda match: line, text)
        else:
            text = text.rstrip('\n') + '\n' + line + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.env-write-', delete=False) as stream:
            temporary = Path(stream.name)
            restrict_file(temporary)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env', help='本机私密 .env 路径')
    parser.add_argument('--mode', choices=('pnvs', 'enterprise'), default='pnvs')
    args = parser.parse_args()
    if not sys.stdin.isatty():
        print('请在本机交互终端运行配置向导；此入口不接收管道中的密钥。')
        return 1
    print('GitHub Secrets 不会自动注入本机。请填写原有短信配置；不会发送短信。')
    print('PNVS 使用号码认证的签名和模板；四项填完后才会保存。')
    try:
        values = {
            'ALIYUN_ACCESS_KEY_ID': getpass.getpass('AccessKey ID（不回显）: '),
            'ALIYUN_ACCESS_KEY_SECRET': getpass.getpass('AccessKey Secret（不回显）: '),
            'ALIYUN_SMS_SIGN_NAME': input('短信签名名称: '),
            'ALIYUN_SMS_TEMPLATE_CODE': input('短信模板 CODE: '),
        }
        write_sms_config(args.env_file, values, args.mode)
        load_env(args.env_file, keys=SMS_KEYS)
    except (EOFError, KeyboardInterrupt):
        print('\n已取消，没有写入配置。')
        return 1
    except UnicodeError:
        print('无法读取原配置；请将文件保存为 UTF-8。')
        return 1
    except ValueError as error:
        print(str(error))
        return 1
    except OSError:
        print('无法保存配置；请检查目录权限。')
        return 1
    print(f'已保存到 {args.env_file}，配置完整：{sms_status()["configured"]}。')
    print('测试验证码已关闭。请重启使用该配置文件的服务，然后用本人号码验证实际收信。')
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
