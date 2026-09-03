from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.email_service import send_email
from app.ws_manager import broadcast

EMAIL_SUBJECTS = {
    models.NotificationTypeEnum.order_confirmed: "Order Confirmation",
    models.NotificationTypeEnum.payment_successful: "Payment Successful",
    models.NotificationTypeEnum.payment_failed: "Payment Failed",
    models.NotificationTypeEnum.order_shipped: "Your Order Has Shipped",
    models.NotificationTypeEnum.order_delivered: "Your Order Has Been Delivered",
    models.NotificationTypeEnum.order_return_requested: "Return Request Update",
    models.NotificationTypeEnum.return_approved: "Return Approved",
    models.NotificationTypeEnum.return_rejected: "Return Rejected",
    models.NotificationTypeEnum.refund_completed: "Refund Completed",
}


def create_notification(
    db: Session,
    user: models.User,
    ntype: "models.NotificationTypeEnum",
    message: str,
    order_id: Optional[str] = None,
) -> models.Notification:
    """Creates the Notification row, sends the matching email, and pushes a
    real-time order_status_updated event over WebSocket to the user."""
    notification = models.Notification(user_id=user.id, type=ntype, message=message)
    db.add(notification)
    db.commit()
    db.refresh(notification)

    send_email(user.email, EMAIL_SUBJECTS.get(ntype, "Order Update"), message)

    broadcast(user.id, "order_status_updated", {
        "notification_id": notification.id,
        "type": ntype.value,
        "message": message,
        "order_id": order_id,
    })

    return notification