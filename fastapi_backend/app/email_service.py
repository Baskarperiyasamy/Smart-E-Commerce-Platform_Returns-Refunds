import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Sends a plain-text email via SMTP. Returns True on success.

    Never raises — if SMTP isn't configured, or sending fails for any
    reason, it logs and returns False instead, so a notification always
    still gets created (and the WebSocket push still fires) even if email
    delivery itself has a problem.
    """
    if not settings.smtp_host or not settings.smtp_username:
        print(f"[email] SMTP not configured — skipped '{subject}' to {to_email}")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{settings.email_from_name} <{settings.email_from or settings.smtp_username}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(msg["From"], [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[email] Failed to send '{subject}' to {to_email}: {e}")
        return False
