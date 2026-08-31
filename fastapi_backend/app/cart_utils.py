from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings


def build_cart_summary(db: Session, user_id: str) -> schemas.CartSummary:
    """Single source of truth for cart totals — used by GET /cart and by
    /checkout, so the amount charged always matches what the user saw."""
    rows = (
        db.query(models.Cart)
        .filter(models.Cart.user_id == user_id)
        .join(models.Product)
        .all()
    )

    items = []
    cart_total = 0.0

    for row in rows:
        product = row.product
        item_total = round(product.price * row.quantity, 2)
        cart_total += item_total
        items.append(
            schemas.CartItemDetail(
                cart_item_id=row.id,
                product_id=product.id,
                product_name=product.name,
                unit_price=product.price,
                quantity=row.quantity,
                item_total=item_total,
                in_stock=product.stock > 0,
            )
        )

    cart_total = round(cart_total, 2)
    tax = round(cart_total * settings.tax_rate, 2)
    grand_total = round(cart_total + tax, 2)

    return schemas.CartSummary(
        items=items,
        item_count=len(items),
        cart_total=cart_total,
        tax_rate=settings.tax_rate,
        tax=tax,
        grand_total=grand_total,
    )
