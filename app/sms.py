"""Cloud SMS for phone login. Prefer Aliyun 短信认证 (personal, no company papers)."""
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


def _env(*names):
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def access_key_ready():
    return bool(_env("ALIYUN_ACCESS_KEY_ID") and _env("ALIYUN_ACCESS_KEY_SECRET"))


def gift_sms_ready():
    return access_key_ready() and bool(_env("ALIYUN_SMS_SIGN_NAME") and _env("ALIYUN_SMS_TEMPLATE_CODE"))


def enterprise_sms_ready():
    return gift_sms_ready() and os.environ.get("ALIYUN_SMS_MODE", "").strip().lower() in {"enterprise", "dysms", "sms"}


def cloud_sms_ready():
    mode = _env("ALIYUN_SMS_MODE").lower()
    return gift_sms_ready() and mode in {"", "pnvs", "enterprise", "dysms", "sms"}


def mac_sms_enabled():
    return os.environ.get("SONGBAI_IMESSAGE") == "1" or os.environ.get("SONGBAI_SMS") == "1"


def must_deliver():
    return cloud_sms_ready() or mac_sms_enabled() or os.environ.get("SONGBAI_REQUIRE_SMS") == "1"


def test_codes_allowed():
    return os.environ.get("SONGBAI_ALLOW_TEST_CODES") == "1"


def sms_status():
    if cloud_sms_ready():
        provider = "aliyun-enterprise" if enterprise_sms_ready() else "aliyun-pnvs"
        return {"ready": True, "configured": True, "delivery_verified": False, "provider": provider, "missing": [],
                "notice": "验证码由阿里云发到手机。这一页不显示数字。"}
    missing = []
    if not access_key_ready():
        missing.append("阿里云 AccessKey")
    if not _env("ALIYUN_SMS_SIGN_NAME"):
        missing.append("赠送签名名称")
    if not _env("ALIYUN_SMS_TEMPLATE_CODE"):
        missing.append("赠送模板 CODE")
    if _env("ALIYUN_SMS_MODE").lower() not in {"", "pnvs", "enterprise", "dysms", "sms"}:
        missing.append("有效的短信模式（pnvs 或 enterprise）")
    return {"ready": False, "configured": False, "delivery_verified": False, "provider": "", "missing": missing,
            "notice": "个人账号不要再填短信服务的企业资质。打开 https://dypns.console.aliyun.com 开通号码认证里的「短信认证」，用系统赠送的签名和模板。再创建 AccessKey，把四项写进松伴文件夹的 .env。"}


def _percent(value):
    return urllib.parse.quote(str(value), safe="-_.~").replace("+", "%20").replace("*", "%2A")


def _signed_get(host, version, params):
    key = _env("ALIYUN_ACCESS_KEY_ID")
    secret = _env("ALIYUN_ACCESS_KEY_SECRET")
    params = {
        **params,
        "AccessKeyId": key,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": version,
    }
    canonical = "&".join(f"{_percent(name)}={_percent(params[name])}" for name in sorted(params))
    string_to_sign = "GET&%2F&" + _percent(canonical)
    params["Signature"] = base64.b64encode(hmac.new((secret + "&").encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()
    url = f"https://{host}/?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            body = json.loads(response.read().decode())
            return body if isinstance(body, dict) else None
    except urllib.error.HTTPError as error:
        # Aliyun may return its structured error in an HTTP 4xx response.
        try:
            body = json.loads(error.read(16384).decode())
            return body if isinstance(body, dict) else None
        except (ValueError, UnicodeError, OSError):
            return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def provider_failure(body):
    """Only approved messages leave the server; never echo provider message/credentials."""
    code = str(body.get("Code") or "") if isinstance(body, dict) else ""
    if code in {"InvalidAccessKeyId.NotFound", "InvalidAccessKeyId", "SignatureDoesNotMatch", "SignatureNonceUsed"}:
        return "短信服务凭据校验失败，请管理员检查 AccessKey。"
    if code.startswith(("Forbidden.RAM", "NoPermission", "Forbidden.AccessKey")):
        return "短信服务权限不足，请管理员检查阿里云 RAM 权限。"
    if code in {"isv.AMOUNT_NOT_ENOUGH", "isv.OUT_OF_SERVICE", "AmountNotEnough", "InsufficientBalance"}:
        return "短信服务余额不足或已停用，请管理员检查阿里云账户。"
    if "SIGN" in code.upper() or "TEMPLATE" in code.upper():
        return "短信签名或模板不可用，请管理员核对当前短信模式与审核状态。"
    if code in {"isv.BUSINESS_LIMIT_CONTROL", "isv.DAY_LIMIT_CONTROL", "Throttling", "Throttling.User"}:
        return "验证码发送过于频繁，请稍后重试。"
    if "MOBILE" in code.upper() or "PHONE" in code.upper():
        return "短信平台未接受这个手机号，请核对号码和支持地区。"
    return "云端短信没有发出，请稍后重试或联系管理员检查短信服务。"


def send_pnvs_code(phone, code):
    """Aliyun 号码认证 · 短信认证. Personal accounts can use gift sign + gift template."""
    body = _signed_get("dypnsapi.aliyuncs.com", "2017-05-25", {
        "Action": "SendSmsVerifyCode",
        "PhoneNumber": phone,
        "SignName": _env("ALIYUN_SMS_SIGN_NAME"),
        "TemplateCode": _env("ALIYUN_SMS_TEMPLATE_CODE"),
        "TemplateParam": json.dumps({"code": code, "min": "10"}, ensure_ascii=False),
        "CodeLength": 6,
        "ValidTime": 600,
        "Interval": 60,
        "CodeType": 1,
        "ReturnVerifyCode": "false",
        "CountryCode": "86",
    })
    if not body:
        return False, "阿里云短信认证没有连上"
    if str(body.get("Code") or "") != "OK" or body.get("Success") is False:
        return False, provider_failure(body)
    return True, "aliyun-pnvs"


def send_aliyun_code(phone, code):
    """Classic dysms SendSms. Needs enterprise signature reporting."""
    body = _signed_get("dysmsapi.aliyuncs.com", "2017-05-25", {
        "Action": "SendSms",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": _env("ALIYUN_SMS_SIGN_NAME"),
        "TemplateCode": _env("ALIYUN_SMS_TEMPLATE_CODE"),
        "TemplateParam": json.dumps({"code": code}, ensure_ascii=False),
    })
    if not body:
        return False, "阿里云短信没有连上"
    if str(body.get("Code") or "") != "OK":
        return False, provider_failure(body)
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
        sender = send_aliyun_code if enterprise_sms_ready() else send_pnvs_code
        sent, detail = sender(phone, code)
        if sent:
            return True, "验证码已由阿里云发到这个手机号。请打开短信填写。这一页不会显示数字。"
        return False, detail
    if mac_sms_enabled():
        sent, detail = send_phone_code(phone, code)
        if sent:
            return True, "验证码已发到这个手机号。请打开短信填写。这一页不会显示数字。"
        return False, "这台电脑没有把短信发出去。没有把数字留在网页上。"
    return False, sms_status()["notice"]
