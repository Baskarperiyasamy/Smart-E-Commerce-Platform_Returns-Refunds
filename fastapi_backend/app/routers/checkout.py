import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.config import settings
from app import models, schemas
from app.cart_utils import build_cart_summary
from app.notification_service import create_notification

router = APIRouter(prefix="/checkout", tags=["Checkout"])


def _stripe_configured():
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe is not configured on the server (.env STRIPE_SECRET_KEY missing).",
        )
    stripe.api_key = settings.stripe_secret_key


@router.post("/", response_model=schemas.CheckoutResponse, status_code=status.HTTP_201_CREATED)
def checkout(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Checkout flow:
      1. Validate the cart (not empty, everything still in stock)
      2. Calculate the total (reusing the exact same math as GET /cart, so
         the amount charged always matches what the user saw)
      3. Create an Order record (+ OrderItem line-item snapshots)
      4. Initialize a Stripe Checkout Session (which also creates the
         underlying Stripe PaymentIntent) for the order total
    """
    _stripe_configured()

    # ---- 1 & 2: validate cart, calculate total ----
    summary = build_cart_summary(db, current_user.id)
    if not summary.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty")

    cart_rows = db.query(models.Cart).filter(models.Cart.user_id == current_user.id).all()
    for row in cart_rows:
        product = db.query(models.Product).filter(models.Product.id == row.product_id).first()
        if not product or product.stock < row.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{product.name if product else row.product_id}' doesn't have enough stock "
                       f"(requested {row.quantity}, available {product.stock if product else 0})",
            )

    # ---- 3: create Order + OrderItem snapshots ----
    order = models.Order(
        user_id=current_user.id,
        total_amount=summary.grand_total,
        order_status=models.OrderStatusEnum.pending,
        payment_status=models.PaymentStatusEnum.pending,
    )
    db.add(order)
    db.flush()  # get order.id before committing

    for item in summary.items:
        db.add(models.OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            product_name=item.product_name,
            unit_price=item.unit_price,
            quantity=item.quantity,
            item_total=item.item_total,
        ))

    # ---- 4: Stripe Checkout Session (creates the PaymentIntent too) ----
    currency = settings.stripe_currency
    line_items = [
        {
            "price_data": {
                "currency": currency,
                "product_data": {"name": item.product_name},
                "unit_amount": round(item.unit_price * 100),
            },
            "quantity": item.quantity,
        }
        for item in summary.items
    ]
    if summary.tax > 0:
        line_items.append({
            "price_data": {
                "currency": currency,
                "product_data": {"name": f"Tax ({summary.tax_rate * 100:.0f}%)"},
                "unit_amount": round(summary.tax * 100),
            },
            "quantity": 1,
        })

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=line_items,
            customer_email=current_user.email,
            success_url=settings.checkout_success_url,
            cancel_url=settings.checkout_cancel_url,
            metadata={"order_id": order.id, "user_id": current_user.id},
            payment_intent_data={"metadata": {"order_id": order.id, "user_id": current_user.id}},
            expand=["payment_intent"],
        )
    except stripe.error.StripeError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe error: {e.user_message or str(e)}")

    payment_intent = session.payment_intent  # expanded object (or None until checkout starts, depending on Stripe version)
    payment_intent_id = payment_intent.id if payment_intent else None
    client_secret = payment_intent.client_secret if payment_intent else None

    order.stripe_checkout_session_id = session.id
    order.stripe_payment_intent_id = payment_intent_id

    db.add(models.Payment(
        order_id=order.id,
        amount=summary.grand_total,
        payment_method="stripe",
        transaction_id=payment_intent_id,
        status=models.PaymentStatusEnum.pending,
    ))

    # Cart is cleared once checkout has been initiated — items are now locked
    # into the order. If payment fails, the order stays as 'cancelled'
    # (set by the webhook) but items aren't silently re-added to the cart.
    for row in cart_rows:
        db.delete(row)

    db.commit()
    db.refresh(order)

    create_notification(
        db, current_user, models.NotificationTypeEnum.order_confirmed,
        f"Your order #{order.id[:8]} has been confirmed. Total: ${summary.grand_total:.2f}",
        order_id=order.id,
    )

    return schemas.CheckoutResponse(
        order_id=order.id,
        checkout_session_id=session.id,
        checkout_url=session.url,
        payment_intent_client_secret=client_secret,
        amount=summary.grand_total,
        currency=currency,
    )
