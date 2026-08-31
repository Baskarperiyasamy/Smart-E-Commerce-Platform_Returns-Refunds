from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app import models, schemas
from app.cart_utils import build_cart_summary
from app.ws_manager import broadcast

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("/", response_model=schemas.CartSummary)
def view_cart(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return build_cart_summary(db, current_user.id)


@router.post("/add", response_model=schemas.CartSummary)
def add_to_cart(
    payload: schemas.CartAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    product = db.query(models.Product).filter(models.Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.stock <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This product is out of stock")

    existing = (
        db.query(models.Cart)
        .filter(models.Cart.user_id == current_user.id, models.Cart.product_id == payload.product_id)
        .first()
    )

    if existing:
        existing.quantity += payload.quantity
    else:
        db.add(models.Cart(user_id=current_user.id, product_id=payload.product_id, quantity=payload.quantity))

    product.popularity += 1
    db.commit()
    summary = build_cart_summary(db, current_user.id)
    broadcast(current_user.id, "cart_updated", summary.model_dump())
    return summary


@router.put("/update", response_model=schemas.CartSummary)
def update_cart_item(
    payload: schemas.CartUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = (
        db.query(models.Cart)
        .filter(models.Cart.id == payload.cart_item_id, models.Cart.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    item.quantity = payload.quantity
    db.commit()
    summary = build_cart_summary(db, current_user.id)
    broadcast(current_user.id, "cart_updated", summary.model_dump())
    return summary


@router.delete("/remove", response_model=schemas.CartSummary)
def remove_from_cart(
    payload: schemas.CartRemove,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = (
        db.query(models.Cart)
        .filter(models.Cart.id == payload.cart_item_id, models.Cart.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    db.delete(item)
    db.commit()
    summary = build_cart_summary(db, current_user.id)
    broadcast(current_user.id, "cart_updated", summary.model_dump())
    return summary


@router.get("/all", response_model=list[schemas.AdminCartItem])
def list_all_carts(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
):
    """Admin-only — powers the frontend's Database Viewer 'Cart Items' tab."""
    rows = db.query(models.Cart).join(models.Product).join(models.User).all()
    return [
        schemas.AdminCartItem(
            cart_item_id=row.id,
            user_id=row.user.id,
            user_name=row.user.name,
            user_email=row.user.email,
            product_id=row.product.id,
            product_name=row.product.name,
            unit_price=row.product.price,
            quantity=row.quantity,
            item_total=round(row.product.price * row.quantity, 2),
        )
        for row in rows
    ]
