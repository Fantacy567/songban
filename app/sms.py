"""Cloud SMS for phone login. Aliyun first, like other Chinese apps. No secrets in responses."""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def cloud_sms_ready():
    return all(os.environ.get(name, "").strip() for name in (
        "ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIYUN_SMS_SIGN_NAME", "ALIYUN_SMS_TEMPLATE_CODE",
    ))


def mac_sms_enabled():
    return os.environ.get("SONGBAI_IMESSAGE") == "1" or os.environ.get("SONGBAI_SMS") == "1"


def must_deliver():
    return cloud_sms_ready() or mac_sms_enabled() or os.environ.get("SONGBAI_REQUIRE_SMS") == "1"


def sms_status():
    if cloud_sms_ready():
        return {"ready": True, "provider": "aliyun", "missing": [],
                "notice": "验证码由阿里云短信发到手机，和常用 App 一样。这一页不显示数字。"}
    missing = []
    if not os.environ.get("ALIYUN_ACCESS_KEY_ID", "").strip() or not os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "").strip():
        missing.append("阿里云 AccessKey")
    if not os.environ.get("ALIYUN_SMS_SIGN_NAME", "").strip():
        missing.append("已审核的短信签名")
    if not os.environ.get("ALIYUN_SMS_TEMPLATE_CODE", "").strip():
        missing.append("已审核的验证码模板")
    return {"ready": False, "provider": "", "missing": missing,
            "notice": "验证码要像常用 App 一样从云端发到手机。还缺：" + "、".join(missing) + "。先打开 https://www.aliyun.com 登录，再打开 https://dysms.console.aliyun.com 开通短信服务。国内短信签名目前要企业资质才能报备。审核通过后把四项写进松伴文件夹的 .env。"}


def _percent(value):
    return urllib.parse.quote(str(value), safe="-_.~").replace("+", "%20").replace("*", "%2A")


def send_aliyun_code(phone, code):
    key = os.environ["ALIYUN_ACCESS_KEY_ID"].strip()
    secret = os.environ["ALIYUN_ACCESS_KEY_SECRET"].strip()
    params = {
        "AccessKeyId": key,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": os.environ["ALIYUN_SMS_SIGN_NAME"].strip(),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": os.environ["ALIYUN_SMS_TEMPLATE_CODE"].strip(),
        "TemplateParam": json.dumps({"code": code}, ensure_ascii=False),
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2017-05-25",
    }
    canonical = "&".join(f"{_percent(name)}={_percent(params[name])}" for name in sorted(params))
    string_to_sign = "GET&%2F&" + _percent(canonical)
    params["Signature"] = base64.b64encode(hmac.new((secret + "&").encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()
    url = "https://dysmsapi.aliyuncs.com/?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            body = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False, "阿里云短信没有连上"
    if str(body.get("Code") or "") != "OK":
        return False, "阿里云没有发出这条短信"
    return True, "aliyun"


def send_phone_code(phone, code):
    handle = "+86" + phone if len(phone) == 11 and phone.startswith("1") else ("+" + phone.lstrip("+"))
    text = f"【松伴】验证码 {code}，10 分钟内有效。如非本人操作请忽略。"
    script = """on run argv
set targetHandle to item 1 of argv
set msg to item 2 of argv
tell application "Messages"
    try
        send msg to participant targetHandle of (first service whose service type is SMS)
        return "sms"
    end try
    try
        send msg to buddy targetHandle of (first service whose service type is SMS)
        return "sms"
    end try
    try
        send msg to participant targetHandle of (first service whose service type is iMessage)
        return "imessage"
    end try
end tell
error "这台 Mac 没有把短信发出去"
end run"""
    try:
        result = subprocess.run(["osascript", "-e", script, handle, text], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False, "信息 App 没有在时限内响应"
    kind = (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""
    if result.returncode != 0 or kind not in {"sms", "imessage"}:
        return False, "信息 App 没有把这条发出去"
    return True, kind


def deliver_login_code(phone, code):
    if cloud_sms_ready():
        sent, detail = send_aliyun_code(phone, code)
        if sent:
            return True, "验证码已由阿里云发到这个手机号。请打开短信填写。这一页不会显示数字。"
        return False, "云端短信没有发出。没有把数字留在网页上。"
    if mac_sms_enabled():
        sent, detail = send_phone_code(phone, code)
        if sent:
            return True, "验证码已发到这个手机号。请打开短信填写。这一页不会显示数字。"
        return False, "这台电脑没有把短信发出去。没有把数字留在网页上。"
    return False, sms_status()["notice"]
