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
    quantity: int = Field(..., gt=0)


class CartRemove(BaseModel):
    cart_item_id: str


class CartOut(BaseModel):
    id: str
    product_id: str
    quantity: int

    class Config:
        from_attributes = True


class CartItemDetail(BaseModel):
    cart_item_id: str
    product_id: str
    product_name: str
    unit_price: float
    quantity: int
    item_total: float
    in_stock: bool


class CartSummary(BaseModel):
    items: list[CartItemDetail]
    item_count: int
    cart_total: float
    tax_rate: float
    tax: float
    grand_total: float


# ---------- Admin / Database Viewer ----------

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


# ---------- Orders / Payments ----------

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


# ---------- Returns ----------

class ReturnRequestCreate(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)
    comment: Optional[str] = Field(None, max_length=1000)


class ReturnRequestOut(BaseModel):
    id: str
    order_id: str
    user_id: str
    reason: str
    comment: Optional[str]
    admin_note: Optional[str] = None
    status: ReturnStatusEnum
    created_at: datetime

    class Config:
        from_attributes = True


class ReturnDecisionRequest(BaseModel):
    """Optional body for POST /admin/returns/{id}/approve and /reject —
    lets the admin leave a note explaining the decision, sent to the
    customer as part of their notification/email."""
    admin_note: Optional[str] = Field(None, max_length=1000)


class OrderOut(BaseModel):
    id: str
    user_id: str
    total_amount: float
    order_status: OrderStatusEnum
    payment_status: PaymentStatusEnum
    stripe_checkout_session_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    items: list[OrderItemOut]
    payments: list[PaymentOut] = []
    return_request: Optional[ReturnRequestOut] = None

    class Config:
        from_attributes = True


class AdminReturnRequestOut(BaseModel):
    """Used by GET /admin/returns — embeds the full order so the admin
    frontend can show tracking dates, items, and totals without a second
    API call per row."""
    id: str
    order_id: str
    user_id: str
    reason: str
    comment: Optional[str]
    admin_note: Optional[str] = None
    status: ReturnStatusEnum
    created_at: datetime
    order: OrderOut

    class Config:
        from_attributes = True


class CheckoutResponse(BaseModel):
    order_id: str
    checkout_session_id: str
    checkout_url: str
    payment_intent_client_secret: Optional[str] = None
    amount: float
    currency: str


class OrderStatusUpdate(BaseModel):
    order_status: OrderStatusEnum


# ---------- Notifications ----------

class NotificationOut(BaseModel):
    id: str
    type: NotificationTypeEnum
    message: str
    read_status: bool
    timestamp: datetime

    class Config:
        from_attributes = True


class NotificationMarkRead(BaseModel):
    notification_id: Optional[str] = None