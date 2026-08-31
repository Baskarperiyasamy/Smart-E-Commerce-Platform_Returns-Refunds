from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app import models, schemas
from app.notification_service import create_notification

router = APIRouter(prefix="/orders", tags=["Returns"])

# How many days after delivery a customer is allowed to request a return.
RETURN_WINDOW_DAYS = 7


@router.post("/{order_id}/return", response_model=schemas.ReturnRequestOut, status_code=status.HTTP_201_CREATED)
def request_return(
    order_id: str,
    payload: schemas.ReturnRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Customer-facing: request a return/refund for one of their own orders.

    Eligibility (checked in this order, so the customer gets the most
    specific error message):
      1. The order must belong to the current user.
      2. order_status must be 'delivered' (can't return something that
         hasn't shipped, and can't double-submit once a return is already
         in progress).
      3. Must be within RETURN_WINDOW_DAYS of the order being marked
         delivered. Order.updated_at is bumped by SQLAlchemy's
         onupdate=datetime.utcnow every time order_status changes, so the
         most recent bump IS the moment this order became 'delivered' —
         that's what starts the return-window clock.
      4. Only one return request is allowed per order.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")

    if order.order_status != models.OrderStatusEnum.delivered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Returns can only be requested for orders that have been delivered.",
        )

    delivered_at = order.updated_at or order.created_at
    deadline = delivered_at + timedelta(days=RETURN_WINDOW_DAYS)
    if datetime.utcnow() > deadline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The {RETURN_WINDOW_DAYS}-day return window for this order has passed.",
        )

    if order.return_request is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A return has already been requested for this order.",
        )

    return_request = models.ReturnRequest(
        order_id=order.id,
        user_id=current_user.id,
        reason=payload.reason,
        comment=payload.comment,
        status=models.ReturnStatusEnum.pending,
    )
    db.add(return_request)

    # Task requirement: when a return is requested, the order status moves
    # to "Return Requested".
    order.order_status = models.OrderStatusEnum.return_requested

    db.commit()
    db.refresh(return_request)

    create_notification(
        db, current_user, models.NotificationTypeEnum.order_return_requested,
        f"Your return request for order #{order.id[:8]} has been submitted and is pending review.",
        order_id=order.id,
    )

    return return_request


@router.get("/{order_id}/return", response_model=schemas.ReturnRequestOut)
def get_return_request(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Fetch the return request (if any) for one order — lets the frontend
    show its current status (pending/approved/rejected) without re-deriving
    it client-side."""
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.user_id != current_user.id and current_user.role.value not in ("admin", "staff"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")

    if order.return_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No return request for this order")

    return order.return_request


@router.get("/returns/all", response_model=list[schemas.ReturnRequestOut])
def list_all_return_requests(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin", "staff")),
):
    """Admin/staff-only read view of every return request — mirrors the
    pattern already used by GET /orders/all and GET /cart/all. Approving or
    rejecting a return is done from the Django Admin panel
    (storefront.ReturnRequestAdmin), same as every other staff action that
    changes order status in this project."""
    return db.query(models.ReturnRequest).order_by(models.ReturnRequest.created_at.desc()).all()
