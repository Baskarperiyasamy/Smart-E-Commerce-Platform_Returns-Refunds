"""
These models map onto the exact same MySQL tables the FastAPI backend
(fastapi_backend/app/models.py) already created and owns. Every model here
has `managed = False`, so Django will never try to create, alter, or drop
these tables — it only reads and writes the rows, through the same schema
SQLAlchemy defined. This is what lets one admin panel manage data that a
completely separate FastAPI process also reads and writes.
"""
import uuid

from django.db import models


def gen_uuid():
    return str(uuid.uuid4())


ROLE_CHOICES = [
    ("admin", "Admin"),
    ("staff", "Staff"),
    ("customer", "Customer"),
]

ORDER_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("paid", "Paid"),
    ("shipped", "Shipped"),
    ("delivered", "Delivered"),
    ("return_requested", "Return Requested"),  # Day 5: Customer Experience & Insights Module
    ("cancelled", "Cancelled"),
]

PAYMENT_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("paid", "Paid"),
    ("failed", "Failed"),
    ("refunded", "Refunded"),
]

NOTIFICATION_TYPE_CHOICES = [
    ("order_confirmed", "Order Confirmed"),
    ("payment_successful", "Payment Successful"),
    ("payment_failed", "Payment Failed"),
    ("order_shipped", "Order Shipped"),
    ("order_delivered", "Order Delivered"),
    ("order_return_requested", "Return Request Update"),  # Day 5
]

# Day 5: Customer Experience & Insights Module — Returns / Refunds
RETURN_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


class EcommerceUser(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=255, unique=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")
    auth_provider = models.CharField(max_length=50, default="local")
    auth0_sub = models.CharField(max_length=255, null=True, blank=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(editable=False)

    class Meta:
        managed = False
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.name} <{self.email}>"


class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    price = models.FloatField()
    stock = models.IntegerField(default=0)
    images = models.TextField(null=True, blank=True, help_text="Comma-separated image URLs.")
    category = models.CharField(max_length=100, null=True, blank=True, default="general")
    popularity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "products"
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        from django.conf import settings
        return self.stock < settings.LOW_STOCK_THRESHOLD


class Cart(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    user = models.ForeignKey(EcommerceUser, on_delete=models.DO_NOTHING, db_column="user_id", related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING, db_column="product_id", related_name="cart_rows")
    quantity = models.IntegerField(default=1)

    class Meta:
        managed = False
        db_table = "cart"
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"

    def __str__(self):
        return f"{self.user} — {self.product} x{self.quantity}"


class Order(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    user = models.ForeignKey(EcommerceUser, on_delete=models.DO_NOTHING, db_column="user_id", related_name="orders")
    total_amount = models.FloatField(default=0.0)
    order_status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default="pending")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending")
    stripe_checkout_session_id = models.CharField(max_length=255, null=True, blank=True, editable=False)
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True, editable=False)
    created_at = models.DateTimeField(editable=False)
    updated_at = models.DateTimeField(editable=False)

    class Meta:
        managed = False
        db_table = "orders"
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{str(self.id)[:8]}"

    @property
    def short_id(self):
        return str(self.id)[:8]


class OrderItem(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    order = models.ForeignKey(Order, on_delete=models.DO_NOTHING, db_column="order_id", related_name="items")
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING, db_column="product_id", related_name="order_lines")
    product_name = models.CharField(max_length=255)
    unit_price = models.FloatField()
    quantity = models.IntegerField()
    item_total = models.FloatField()

    class Meta:
        managed = False
        db_table = "order_items"
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class Payment(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    order = models.ForeignKey(Order, on_delete=models.DO_NOTHING, db_column="order_id", related_name="payments")
    amount = models.FloatField()
    payment_method = models.CharField(max_length=50, default="stripe")
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending")
    timestamp = models.DateTimeField(editable=False)

    class Meta:
        managed = False
        db_table = "payments"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"Payment {str(self.id)[:8]} — {self.status}"


class Notification(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    user = models.ForeignKey(EcommerceUser, on_delete=models.DO_NOTHING, db_column="user_id", related_name="notifications")
    type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    message = models.CharField(max_length=500)
    read_status = models.BooleanField(default=False)
    timestamp = models.DateTimeField(editable=False)

    class Meta:
        managed = False
        db_table = "notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.type} — {self.user}"


class ReturnRequest(models.Model):
    """Day 5: Customer Experience & Insights Module.
    Mirrors app/models.py::ReturnRequest in the FastAPI backend — same
    table (return_requests), unmanaged here since FastAPI/SQLAlchemy owns
    the schema. Staff approve/reject a return from this admin (see
    storefront/admin.py::ReturnRequestAdmin)."""
    id = models.CharField(primary_key=True, max_length=36, default=gen_uuid, editable=False)
    order = models.OneToOneField(
        Order, on_delete=models.DO_NOTHING, db_column="order_id", related_name="return_request"
    )
    user = models.ForeignKey(
        EcommerceUser, on_delete=models.DO_NOTHING, db_column="user_id", related_name="return_requests"
    )
    reason = models.CharField(max_length=255)
    comment = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=RETURN_STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(editable=False)

    class Meta:
        managed = False
        db_table = "return_requests"
        verbose_name = "Return Request"
        verbose_name_plural = "Return Requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return {str(self.id)[:8]} — {self.status}"
