from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def send_member_qr_email(
    recipient_email: str,
    member_name: str,
    qr_image_path: str,
    qr_token: str,
) -> tuple[bool, str]:
    sender_email = os.getenv("GYM_SMTP_EMAIL", "").strip()
    app_password = os.getenv("GYM_SMTP_PASSWORD", "").strip()
    smtp_host = os.getenv("GYM_SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("GYM_SMTP_PORT", "587"))

    if not sender_email or not app_password:
        return False, "Set GYM_SMTP_EMAIL and GYM_SMTP_PASSWORD first."

    qr_path = Path(qr_image_path)
    if not qr_path.exists():
        return False, "QR image file was not found."

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = recipient_email
    message["Subject"] = "Gym QR Code"
    message.set_content(
        f"Hello {member_name},\n\n"
        "Your gym QR code is attached to this email.\n"
        "Please show this QR code when paying with your credits.\n\n"
        f"QR token: {qr_token}\n"
    )

    with qr_path.open("rb") as file:
        message.add_attachment(
            file.read(),
            maintype="image",
            subtype="png",
            filename=qr_path.name,
        )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, app_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"Email failed: {exc}"

    return True, "QR email sent successfully."
