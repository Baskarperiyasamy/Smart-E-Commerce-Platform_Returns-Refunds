from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app import models, schemas
from app.notification_service import create_notification

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/", response_model=list[schemas.OrderOut])
def list_my_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Order)
        .filter(models.Order.user_id == current_user.id)
        .order_by(models.Order.created_at.desc())
        .all()
    )


@router.get("/all", response_model=list[schemas.OrderOut])
def list_all_orders(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin", "staff")),
):
    return db.query(models.Order).order_by(models.Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.user_id != current_user.id and current_user.role.value not in ("admin", "staff"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")

    return order


@router.put("/{order_id}/status", response_model=schemas.OrderOut)
def update_order_status(
    order_id: str,
    payload: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin", "staff")),
):
    """Admin/staff-only. Also records shipped_at/delivered_at timestamps
    used for tracking display on the admin frontend."""
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order.order_status = payload.order_status

    if payload.order_status == models.OrderStatusEnum.shipped:
        order.shipped_at = datetime.utcnow()
    elif payload.order_status == models.OrderStatusEnum.delivered:
        order.delivered_at = datetime.utcnow()

    db.commit()
    db.refresh(order)

    if payload.order_status == models.OrderStatusEnum.shipped:
        create_notification(
            db, order.user, models.NotificationTypeEnum.order_shipped,
            f"Your order #{order.id[:8]} has shipped.", order_id=order.id,
        )
    elif payload.order_status == models.OrderStatusEnum.delivered:
        create_notification(
            db, order.user, models.NotificationTypeEnum.order_delivered,
            f"Your order #{order.id[:8]} has been delivered.", order_id=order.id,
        )

    return order