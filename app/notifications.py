from __future__ import annotations

import base64
import os
import smtplib
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from typing import Dict, Iterable

from app.database import add_parent_notification


def send_email(to_email: str, subject: str, message: str) -> bool:
    host = os.getenv("SMTP_HOST")
    if not host:
        raise RuntimeError("SMTP_HOST ayarlanmamış. Gerçek e-posta gönderimi için SMTP_HOST tanımlanmalıdır.")

    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM_EMAIL", username or "noreply@localhost")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    msg = MIMEText(message, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    if use_ssl:
        with smtplib.SMTP_SSL(host, port) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        return True

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)
    return True


def send_sms_via_twilio(to_number: str, body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_number]):
        raise RuntimeError("Twilio ayarları eksik. TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN ve TWILIO_FROM_NUMBER tanımlanmalıdır.")

    payload = urllib.parse.urlencode({
        "Body": body,
        "To": to_number,
        "From": from_number,
    }).encode("utf-8")
    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=payload,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        status = getattr(response, "status", response.getcode())
        return status in {200, 201, 202}


def deliver_parent_notifications(
    student_name: str,
    *,
    channel: str,
    email: str = "",
    phone: str = "",
    subject: str,
    message: str,
) -> Dict[str, bool]:
    results: Dict[str, bool] = {"email": False, "sms": False}
    channels: Iterable[str]
    if channel == "email":
        channels = ["email"]
    elif channel == "sms":
        channels = ["sms"]
    else:
        channels = ["email", "sms"]

    try:
        for current in channels:
            if current == "email" and email:
                send_email(email, subject, message)
                add_parent_notification(student_name, "email", email, message, "Gönderildi")
                results["email"] = True
            elif current == "sms" and phone:
                send_sms_via_twilio(phone, message)
                add_parent_notification(student_name, "sms", phone, message, "Gönderildi")
                results["sms"] = True
    except RuntimeError:
        for current in channels:
            if current == "email" and email:
                add_parent_notification(student_name, "email", email, message, "Hata")
            elif current == "sms" and phone:
                add_parent_notification(student_name, "sms", phone, message, "Hata")
        return results
    except Exception:
        for current in channels:
            if current == "email" and email:
                add_parent_notification(student_name, "email", email, message, "Hata")
            elif current == "sms" and phone:
                add_parent_notification(student_name, "sms", phone, message, "Hata")
        return results

    return results
