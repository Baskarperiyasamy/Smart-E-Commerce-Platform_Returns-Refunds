import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app import models
from app.notification_service import create_notification

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _mark_order_paid(db: Session, order: models.Order, payment_intent_id: str | None):
    order.payment_status = models.PaymentStatusEnum.paid
    if order.order_status == models.OrderStatusEnum.pending:
        order.order_status = models.OrderStatusEnum.paid
    if payment_intent_id:
        order.stripe_payment_intent_id = payment_intent_id

    payment = db.query(models.Payment).filter(models.Payment.order_id == order.id).first()
    if payment:
        payment.status = models.PaymentStatusEnum.paid
        if payment_intent_id:
            payment.transaction_id = payment_intent_id

    # Decrement stock now that payment is confirmed
    for item in order.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product:
            product.stock = max(0, product.stock - item.quantity)


def _mark_order_failed(db: Session, order: models.Order):
    order.payment_status = models.PaymentStatusEnum.failed
    order.order_status = models.OrderStatusEnum.cancelled

    payment = db.query(models.Payment).filter(models.Payment.order_id == order.id).first()
    if payment:
        payment.status = models.PaymentStatusEnum.failed


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Configure this URL in the Stripe Dashboard (or via `stripe listen
    --forward-to localhost:8000/webhooks/stripe` for local testing):

        Events to send: checkout.session.completed,
                         checkout.session.async_payment_failed,
                         payment_intent.payment_failed
    """
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret is not configured (.env STRIPE_WEBHOOK_SECRET missing).",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    event_type = event["type"]
    # Newer stripe-python versions return a StripeObject that supports
    # item access (obj["key"]) but NOT .get(...) — calling .get() on it
    # raises "'get' is a dict method, but a Session is not a dict".
    # .to_dict() converts it (recursively) into a real Python dict so
    # .get() works normally everywhere below.
    data_object = event["data"]["object"].to_dict()

    if event_type == "checkout.session.completed":
        order_id = data_object.get("metadata", {}).get("order_id")
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if order:
            _mark_order_paid(db, order, data_object.get("payment_intent"))
            db.commit()
            create_notification(
                db, order.user, models.NotificationTypeEnum.payment_successful,
                f"Payment of ${order.total_amount:.2f} for order #{order.id[:8]} was successful.",
                order_id=order.id,
            )

    elif event_type in ("checkout.session.async_payment_failed", "payment_intent.payment_failed"):
        order_id = data_object.get("metadata", {}).get("order_id")
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if order:
            _mark_order_failed(db, order)
            db.commit()
            create_notification(
                db, order.user, models.NotificationTypeEnum.payment_failed,
                f"Payment for order #{order.id[:8]} failed. Please try again.",
                order_id=order.id,
            )

    return {"received": True}
