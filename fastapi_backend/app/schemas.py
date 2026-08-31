from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from app.models import RoleEnum, OrderStatusEnum, PaymentStatusEnum, NotificationTypeEnum, ReturnStatusEnum


# ---------- Auth ----------

class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class Auth0LoginRequest(BaseModel):
    # Access token issued by Auth0 after the user completes Google/Facebook login
    auth0_access_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: RoleEnum
    auth_provider: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Product ----------

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int = 0
    images: Optional[str] = None
    category: Optional[str] = "general"
    popularity: int = 0


class ProductOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    price: float
    stock: int
    images: Optional[str]
    category: Optional[str]
    popularity: int

    class Config:
        from_attributes = True


# ---------- Cart ----------

class CartAdd(BaseModel):
    product_id: str
    quantity: int = Field(default=1, gt=0)


class CartUpdate(BaseModel):
    cart_item_id: str
    quantity: int = Field(..., gt=0, description="New quantity. Use DELETE /cart/remove to remove an item entirely.")


class CartRemove(BaseModel):
    cart_item_id: str


class CartOut(BaseModel):
    id: str
    product_id: str
    quantity: int

    class Config:
        from_attributes = True


class CartItemDetail(BaseModel):
    """A single cart line, enriched with product info and the calculated line total."""
    cart_item_id: str
    product_id: str
    product_name: str
    unit_price: float
    quantity: int
    item_total: float
    in_stock: bool


class CartSummary(BaseModel):
    """Full cart view with automatic calculations, per the Day 2 brief."""
    items: list[CartItemDetail]
    item_count: int
    cart_total: float
    tax_rate: float
    tax: float
    grand_total: float


# ---------- Admin / Database Viewer ----------
# Read-only, admin-only views used by the frontend's Database Viewer page,
# so the raw tables can be inspected without Django or a separate DB tool.

class AdminCartItem(BaseModel):
    cart_item_id: str
    user_id: str
    user_name: str
    user_email: str
    product_id: str
    product_name: str
    unit_price: float
    quantity: int
    item_total: float


# ---------- Day 3: Checkout / Orders / Payments ----------

class OrderItemOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    unit_price: float
    quantity: int
    item_total: float

    class Config:
        from_attributes = True


class PaymentOut(BaseModel):
    id: str
    amount: float
    payment_method: str
    transaction_id: Optional[str]
    status: PaymentStatusEnum
    timestamp: datetime

    class Config:
        from_attributes = True


# ---------- Day 5: Customer Experience & Insights Module — Returns ----------
# Defined before OrderOut so OrderOut can embed a return_request.

class ReturnRequestCreate(BaseModel):
    """POST /orders/{order_id}/return body."""
    reason: str = Field(..., min_length=3, max_length=255, description="Why the customer wants to return this order.")
    comment: Optional[str] = Field(None, max_length=1000, description="Optional extra detail from the customer.")


class ReturnRequestOut(BaseModel):
    id: str
    order_id: str
    user_id: str
    reason: str
    comment: Optional[str]
    status: ReturnStatusEnum
    created_at: datetime

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: str
    user_id: str
    total_amount: float
    order_status: OrderStatusEnum
    payment_status: PaymentStatusEnum
    stripe_checkout_session_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
    payments: list[PaymentOut] = []
    return_request: Optional[ReturnRequestOut] = None

    class Config:
        from_attributes = True


class CheckoutResponse(BaseModel):
    """Returned by POST /checkout. Frontend redirects the browser to
    checkout_url to complete payment on Stripe's hosted page."""
    order_id: str
    checkout_session_id: str
    checkout_url: str
    payment_intent_client_secret: Optional[str] = None
    amount: float
    currency: str


class OrderStatusUpdate(BaseModel):
    """Admin/staff use only — to move an order along its fulfilment lifecycle."""
    order_status: OrderStatusEnum


# ---------- Day 4: Notifications ----------

class NotificationOut(BaseModel):
    id: str
    type: NotificationTypeEnum
    message: str
    read_status: bool
    timestamp: datetime

    class Config:
        from_attributes = True


class NotificationMarkRead(BaseModel):
    """POST /notifications/read body. Omit notification_id to mark every
    notification for the current user as read; provide it to mark just one."""
    notification_id: Optional[str] = None
