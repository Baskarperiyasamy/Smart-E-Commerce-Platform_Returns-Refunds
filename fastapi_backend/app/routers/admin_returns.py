import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.config import settings
from app import models, schemas
from app.notification_service import create_notification

router = APIRouter(prefix="/admin/returns", tags=["Admin Returns"])


@router.get("/", response_model=list[schemas.AdminReturnRequestOut])
def list_returns(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin", "staff")),
):
    """GET /admin/returns — every return request, newest first, with the
    full order embedded (items, totals, tracking dates) so the admin
    frontend needs only this one call."""
    return db.query(models.ReturnRequest).order_by(models.ReturnRequest.created_at.desc()).all()


def _restock(db: Session, order: models.Order):
    for item in order.items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        if product:
            product.stock += item.quantity


def _refund_payment(order: models.Order):
    if not settings.stripe_secret_key or not order.stripe_payment_intent_id:
        return None
    stripe.api_key = settings.stripe_secret_key
    try:
        refund = stripe.Refund.create(payment_intent=order.stripe_payment_intent_id)
        return refund.id
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stripe refund failed: {e.user_message or str(e)}",
        )


@router.post("/{return_id}/approve", response_model=schemas.AdminReturnRequestOut)
def approve_return(
    return_id: str,
    payload: schemas.ReturnDecisionRequest = schemas.ReturnDecisionRequest(),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin", "staff")),
):
    ret = db.query(models.ReturnRequest).filter(models.ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return request not found")
    if ret.status != models.ReturnStatusEnum.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This return has already been reviewed.")

    order = ret.order

    ret.status = models.ReturnStatusEnum.approved
    if payload and payload.admin_note:
        ret.admin_note = payload.admin_note
    order.order_status = models.OrderStatusEnum.returned
    _restock(db, order)
    db.commit()
    db.refresh(ret)
    db.refresh(order)

    approve_msg = f"Your return for order #{order.id[:8]} has been approved."
    if payload and payload.admin_note:
        approve_msg += f" Note from our team: {payload.admin_note}"
    create_notification(
        db, ret.user, models.NotificationTypeEnum.return_approved, approve_msg, order_id=order.id,
    )

    refund_id = _refund_payment(order)
    order.payment_status = models.PaymentStatusEnum.refunded
    payment = db.query(models.Payment).filter(models.Payment.order_id == order.id).first()
    if payment:
        payment.status = models.PaymentStatusEnum.refunded
        if refund_id:
            payment.transaction_id = refund_id
    db.commit()

    create_notification(
        db, ret.user, models.NotificationTypeEnum.refund_completed,
        f"Your refund for order #{order.id[:8]} has been completed.",
        order_id=order.id,
    )

    db.refresh(ret)
    return ret


@router.post("/{return_id}/reject", response_model=schemas.AdminReturnRequestOut)
def reject_return(
    return_id: str,
    payload: schemas.ReturnDecisionRequest = schemas.ReturnDecisionRequest(),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin", "staff")),
):
    ret = db.query(models.ReturnRequest).filter(models.ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return request not found")
    if ret.status != models.ReturnStatusEnum.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This return has already been reviewed.")

    order = ret.order
    ret.status = models.ReturnStatusEnum.rejected
    if payload and payload.admin_note:
        ret.admin_note = payload.admin_note
    order.order_status = models.OrderStatusEnum.delivered
    db.commit()
    db.refresh(ret)

    reject_msg = f"Your return request for order #{order.id[:8]} was reviewed and rejected."
    if payload and payload.admin_note:
        reject_msg += f" Reason: {payload.admin_note}"
    create_notification(
        db, ret.user, models.NotificationTypeEnum.return_rejected, reject_msg, order_id=order.id,
    )

    return ret