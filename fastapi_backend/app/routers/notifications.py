from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import models, schemas

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", response_model=list[schemas.NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Every notification for the logged-in user, newest first."""
    return (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.timestamp.desc())
        .all()
    )


@router.post("/read", response_model=list[schemas.NotificationOut])
def mark_notifications_read(
    payload: schemas.NotificationMarkRead,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Marks one notification as read (pass notification_id), or every
    notification for the current user if notification_id is omitted."""
    query = db.query(models.Notification).filter(models.Notification.user_id == current_user.id)
    if payload.notification_id:
        query = query.filter(models.Notification.id == payload.notification_id)

    query.update({"read_status": True}, synchronize_session=False)
    db.commit()

    return (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.timestamp.desc())
        .all()
    )
