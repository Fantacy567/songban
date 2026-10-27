#!/usr/bin/env python3
"""Write Aliyun AccessKey into .env and print SMS readiness."""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def upsert_env(key: str, value: str) -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    ENV.write_text(text, encoding="utf-8")


def main() -> int:
    if not ENV.exists():
        print(f"缺少 {ENV}，请先从 .env.example 复制。")
        return 1
    print("阿里云 AccessKey 只显示一次，请从 RAM 页面复制后粘贴到这里。")
    print("（签名和模板已写在 .env，一般不用改。）\n")
    key_id = input("AccessKey ID: ").strip()
    if not key_id:
        print("未填写 ID，已取消。")
        return 1
    secret = getpass.getpass("AccessKey Secret（输入时不会显示）: ").strip()
    if not secret:
        print("未填写 Secret，已取消。")
        return 1
    upsert_env("ALIYUN_ACCESS_KEY_ID", key_id)
    upsert_env("ALIYUN_ACCESS_KEY_SECRET", secret)
    print(f"\n已写入 {ENV}")
    sys.path.insert(0, str(ROOT))
    from app.main import load_env

    load_env()
    from app.sms import sms_status

    status = sms_status()
    print("短信状态:", status.get("notice") or status)
    if status.get("ready"):
        print("\n请重启松伴服务（终端里 Ctrl+C 后重新 uvicorn），再在注册页点「获取验证码」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
