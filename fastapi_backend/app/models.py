import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, Enum, Text, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    admin = "admin"
    staff = "staff"
    customer = "customer"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)

    # Nullable because social-login (Auth0) users may not have a local password
    password_hash = Column(String(255), nullable=True)

    role = Column(Enum(RoleEnum), default=RoleEnum.customer, nullable=False)

    # Social login metadata
    auth_provider = Column(String(50), default="local")  # local | google | facebook
    auth0_sub = Column(String(255), unique=True, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cart_items = relationship("Cart", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    images = Column(Text, nullable=True)  # comma-separated URLs (keep simple for Day 1)
    category = Column(String(100), nullable=True, index=True, default="general")
    popularity = Column(Integer, default=0)  # simple counter: bump on each purchase/add-to-cart
    created_at = Column(DateTime, default=datetime.utcnow)

    cart_items = relationship("Cart", back_populates="product", cascade="all, delete-orphan")


class Cart(Base):
    __tablename__ = "cart"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")


# ---------------------------------------------------------------------
# Day 3: Checkout + Stripe payments
# ---------------------------------------------------------------------

class OrderStatusEnum(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    shipped = "shipped"
    delivered = "delivered"
    return_requested = "return_requested"  # Day 5: Customer Experience & Insights Module
    cancelled = "cancelled"


class PaymentStatusEnum(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    total_amount = Column(Float, default=0.0)

    # Split, per the Day 3 brief: order_status tracks fulfilment,
    # payment_status tracks money. A shipped order is always payment_status=paid,
    # but a paid order isn't necessarily shipped yet.
    order_status = Column(Enum(OrderStatusEnum), default=OrderStatusEnum.pending, nullable=False)
    payment_status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.pending, nullable=False)

    # Stripe references, so the webhook can find this order again
    stripe_checkout_session_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    # NOTE: also doubles as the "delivered at" timestamp for the Day 5 return
    # window check — it's bumped by onupdate=datetime.utcnow every time
    # order_status changes, so the last bump is when 'delivered' was set.
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    return_request = relationship(
        "ReturnRequest", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )


class OrderItem(Base):
    """A line item snapshot of what was purchased, copied from the Cart at
    checkout time (so later price/name changes on Product don't rewrite history)."""
    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)

    product_name = Column(String(255), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    item_total = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)

    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), default="stripe")  # stripe | card | etc.
    transaction_id = Column(String(255), nullable=True, index=True)  # Stripe PaymentIntent/charge id
    status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.pending, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="payments")


# ---------------------------------------------------------------------
# Day 4: Notifications
# ---------------------------------------------------------------------

class NotificationTypeEnum(str, enum.Enum):
    order_confirmed = "order_confirmed"
    payment_successful = "payment_successful"
    payment_failed = "payment_failed"
    order_shipped = "order_shipped"
    order_delivered = "order_delivered"
    order_return_requested = "order_return_requested"  # Day 5


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    type = Column(Enum(NotificationTypeEnum), nullable=False)
    message = Column(String(500), nullable=False)
    read_status = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")


# ---------------------------------------------------------------------
# Day 5: Customer Experience & Insights Module — Returns / Refunds
# ---------------------------------------------------------------------

class ReturnStatusEnum(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ReturnRequest(Base):
    """Customer-initiated return/refund request for a delivered order.
    One return request per order (order_id is unique) — approving/rejecting
    is handled by staff from the Django Admin panel."""
    __tablename__ = "return_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), unique=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    reason = Column(String(255), nullable=False)
    comment = Column(Text, nullable=True)
    status = Column(Enum(ReturnStatusEnum), default=ReturnStatusEnum.pending, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="return_request")
    user = relationship("User")
