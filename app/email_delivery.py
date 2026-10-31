"""QQ SMTP delivery. Configuration and authorization codes stay on the server."""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


EMAIL_KEYS = frozenset({'QQ_SMTP_EMAIL', 'QQ_SMTP_AUTH_CODE'})


def normalize_email(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if len(value) > 254 or value.count('@') != 1:
        return None
    local, domain = value.split('@')
    if (not local or len(local) > 64 or local.startswith('.') or local.endswith('.')
            or '..' in local or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)):
        return None
    labels = domain.split('.')
    if len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        return None
    return value


def email_status():
    sender = normalize_email(os.environ.get('QQ_SMTP_EMAIL', ''))
    ready = bool(sender and sender.split('@')[1] in {'qq.com', 'foxmail.com'}
                 and os.environ.get('QQ_SMTP_AUTH_CODE', '').strip())
    # Presence only, never a claim that the SMTP credentials have been verified.
    return {'ready': ready, 'provider': 'QQ邮箱', 'registration_available': ready}


def deliver_email_code(recipient, code, purpose='login'):
    if not email_status()['ready']:
        raise RuntimeError('邮箱登录暂不可用，请联系管理员配置发件邮箱。')
    sender = os.environ['QQ_SMTP_EMAIL'].strip().lower()
    message = EmailMessage()
    message['From'] = formataddr(('松伴', sender))
    message['To'] = recipient
    message['Subject'] = '松伴邮箱验证码'
    action = '绑定邮箱' if purpose == 'bind' else '登录或注册'
    message.set_content(f'你正在松伴{action}。\n\n验证码：{code}\n\n有效期为 10 分钟，仅可使用一次。请勿向他人透露验证码。\n如果不是你本人操作，请忽略本邮件。\n')
    try:
        with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=12, context=ssl.create_default_context()) as smtp:
            smtp.login(sender, os.environ['QQ_SMTP_AUTH_CODE'].strip())
            refused = smtp.send_message(message)
            if refused:
                raise RuntimeError('recipient refused')
    except (OSError, smtplib.SMTPException, RuntimeError):
        # SMTP exceptions can contain recipient addresses or authentication data.
        raise RuntimeError('验证码邮件未能发送，请稍后重试或联系管理员。') from None
