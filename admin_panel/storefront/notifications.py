"""
Mirrors app/notification_service.py + app/email_service.py from the FastAPI
backend, so that changing an order's status from the Django Admin panel
notifies the customer exactly the same way the FastAPI API does (a
Notification row + an email).

One honest limitation: the live WebSocket push (/ws/notifications) only
works for changes made through the FastAPI API, because those open
WebSocket connections live in the FastAPI process's memory — this is a
completely separate Django process and has no way to reach into them. A
change made here still creates the Notification row and sends the email;
the customer will just see it on their next page load/refresh of
notifications.html instead of instantly. See the README for more on this.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from django.utils import timezone
from django.conf import settings

from storefront.models import Notification

EMAIL_SUBJECTS = {
    "order_confirmed": "Order Confirmation",
    "payment_successful": "Payment Successful",
    "payment_failed": "Payment Failed",
    "order_shipped": "Your Order Has Shipped",
    "order_delivered": "Your Order Has Been Delivered",
    "order_return_requested": "Return Request Update",
}


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not settings.SMTP_HOST or not settings.SMTP_USERNAME:
        print(f"[email] SMTP not configured — skipped '{subject}' to {to_email}")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM or settings.SMTP_USERNAME}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[email] Failed to send '{subject}' to {to_email}: {e}")
        return False


def notify_order_status(order, ntype: str, message: str):
    """Creates the Notification row and sends the matching email. Does NOT
    push a live WebSocket event — see module docstring."""
    Notification.objects.create(user=order.user, type=ntype, message=message, timestamp=timezone.now())
    send_email(order.user.email, EMAIL_SUBJECTS.get(ntype, "Order Update"), message)
