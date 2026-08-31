import uuid

from django import forms
from django.contrib import admin, messages
from django.core.files.storage import default_storage

from storefront.models import (
    Cart, EcommerceUser, Notification, Order, OrderItem, Payment, Product, ReturnRequest,
)
from storefront.notifications import notify_order_status


# ---------------------------------------------------------------------
# 1. User Management — view, edit, assign roles, activate/deactivate
# ---------------------------------------------------------------------

@admin.register(EcommerceUser)
class EcommerceUserAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "role", "is_active", "auth_provider", "created_at")
    list_filter = ("role", "is_active", "auth_provider")
    search_fields = ("name", "email")
    readonly_fields = ("id", "password_hash", "auth0_sub", "created_at")
    fields = ("id", "name", "email", "role", "is_active", "auth_provider", "auth0_sub", "password_hash", "created_at")
    actions = ["activate_users", "deactivate_users", "make_admin", "make_staff", "make_customer"]

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} user(s) activated.", messages.SUCCESS)

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} user(s) deactivated.", messages.SUCCESS)

    @admin.action(description="Assign role: Admin")
    def make_admin(self, request, queryset):
        updated = queryset.update(role="admin")
        self.message_user(request, f"{updated} user(s) set to Admin.", messages.SUCCESS)

    @admin.action(description="Assign role: Staff")
    def make_staff(self, request, queryset):
        updated = queryset.update(role="staff")
        self.message_user(request, f"{updated} user(s) set to Staff.", messages.SUCCESS)

    @admin.action(description="Assign role: Customer")
    def make_customer(self, request, queryset):
        updated = queryset.update(role="customer")
        self.message_user(request, f"{updated} user(s) set to Customer.", messages.SUCCESS)


# ---------------------------------------------------------------------
# 2. Product Management — add, edit, delete, upload images, update stock
# ---------------------------------------------------------------------

class ProductAdminForm(forms.ModelForm):
    image_upload = forms.ImageField(
        required=False,
        help_text="Upload a product image — its URL is appended to the Images field below.",
    )

    class Meta:
        model = Product
        fields = "__all__"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "category", "price", "stock", "low_stock_badge", "popularity")
    list_editable = ("price", "stock")
    list_filter = ("category",)
    search_fields = ("name", "category")

    @admin.display(description="Stock Alert")
    def low_stock_badge(self, obj):
        return "⚠ LOW STOCK" if obj.is_low_stock else ""

    def save_model(self, request, obj, form, change):
        upload = form.cleaned_data.get("image_upload")
        if upload:
            filename = f"products/{obj.id or uuid.uuid4()}_{upload.name}"
            saved_path = default_storage.save(filename, upload)
            url = request.build_absolute_uri("/media/" + saved_path)
            obj.images = (obj.images + "," if obj.images else "") + url
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------
# 3. Order Management — view all orders, update status, track payment
# ---------------------------------------------------------------------

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "unit_price", "quantity", "item_total")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("amount", "payment_method", "transaction_id", "status", "timestamp")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("short_id", "user", "total_amount", "order_status", "payment_status", "created_at")
    list_filter = ("order_status", "payment_status")
    search_fields = ("id", "user__name", "user__email")
    readonly_fields = (
        "id", "user", "total_amount", "payment_status",
        "stripe_checkout_session_id", "stripe_payment_intent_id",
        "created_at", "updated_at",
    )
    fields = (
        "id", "user", "total_amount", "order_status", "payment_status",
        "stripe_checkout_session_id", "stripe_payment_intent_id",
        "created_at", "updated_at",
    )
    inlines = [OrderItemInline, PaymentInline]
    actions = ["mark_shipped", "mark_delivered", "mark_cancelled"]

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change:
            previous_status = Order.objects.get(pk=obj.pk).order_status

        super().save_model(request, obj, form, change)

        if change and previous_status != obj.order_status:
            self._notify(obj, obj.order_status)

    def _notify(self, order, new_status):
        if new_status == "shipped":
            notify_order_status(order, "order_shipped", f"Your order #{order.short_id} has shipped.")
        elif new_status == "delivered":
            notify_order_status(order, "order_delivered", f"Your order #{order.short_id} has been delivered.")

    @admin.action(description="Mark selected orders as Shipped")
    def mark_shipped(self, request, queryset):
        count = 0
        for order in queryset:
            order.order_status = "shipped"
            order.save()
            self._notify(order, "shipped")
            count += 1
        self.message_user(request, f"{count} order(s) marked Shipped and customers notified.", messages.SUCCESS)

    @admin.action(description="Mark selected orders as Delivered")
    def mark_delivered(self, request, queryset):
        count = 0
        for order in queryset:
            order.order_status = "delivered"
            order.save()
            self._notify(order, "delivered")
            count += 1
        self.message_user(request, f"{count} order(s) marked Delivered and customers notified.", messages.SUCCESS)

    @admin.action(description="Mark selected orders as Cancelled")
    def mark_cancelled(self, request, queryset):
        count = queryset.update(order_status="cancelled")
        self.message_user(request, f"{count} order(s) marked Cancelled.", messages.SUCCESS)


# ---------------------------------------------------------------------
# 5. Day 5: Customer Experience & Insights Module — Return/Refund review
# ---------------------------------------------------------------------

@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    """Staff review queue for return requests submitted by customers via
    POST /orders/{order_id}/return. Approving refunds the order (payment
    status -> refunded, order status -> cancelled); rejecting sends the
    order status back to Delivered. Both notify the customer the same way
    OrderAdmin's shipped/delivered actions do."""
    list_display = ("short_id", "order_link", "user", "reason", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "order__id", "user__name", "user__email", "reason")
    readonly_fields = ("id", "order", "user", "reason", "comment", "created_at")
    fields = ("id", "order", "user", "reason", "comment", "status", "created_at")
    ordering = ("-created_at",)
    actions = ["approve_returns", "reject_returns"]

    @admin.display(description="Return ID")
    def short_id(self, obj):
        return str(obj.id)[:8]

    @admin.display(description="Order")
    def order_link(self, obj):
        return obj.order.short_id if obj.order else "—"

    @admin.action(description="Approve selected returns (refunds order, order → Cancelled)")
    def approve_returns(self, request, queryset):
        count = 0
        for ret in queryset.filter(status="pending"):
            ret.status = "approved"
            ret.save()

            order = ret.order
            order.payment_status = "refunded"
            order.order_status = "cancelled"
            order.save()

            notify_order_status(
                order, "order_return_requested",
                f"Your return for order #{order.short_id} was approved and has been refunded.",
            )
            count += 1
        self.message_user(request, f"{count} return(s) approved and refunded.", messages.SUCCESS)

    @admin.action(description="Reject selected returns (order stays Delivered)")
    def reject_returns(self, request, queryset):
        count = 0
        for ret in queryset.filter(status="pending"):
            ret.status = "rejected"
            ret.save()

            order = ret.order
            order.order_status = "delivered"
            order.save()

            notify_order_status(
                order, "order_return_requested",
                f"Your return request for order #{order.short_id} was reviewed and rejected.",
            )
            count += 1
        self.message_user(request, f"{count} return(s) rejected.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False


# ---------------------------------------------------------------------
# Supporting read-only registrations (useful for admins to inspect,
# not part of the three management tasks above)
# ---------------------------------------------------------------------

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "quantity")
    search_fields = ("user__name", "user__email", "product__name")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "message", "read_status", "timestamp")
    list_filter = ("type", "read_status")
    search_fields = ("user__name", "user__email", "message")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Standalone Payments list — filter by 'status' to see completed
    (paid) vs. not-completed (pending/failed/refunded) at a glance,
    without opening each order individually."""
    list_display = ("short_id", "order_link", "amount", "payment_method", "status", "transaction_id", "timestamp")
    list_filter = ("status", "payment_method")
    search_fields = ("id", "transaction_id", "order__id", "order__user__name", "order__user__email")
    readonly_fields = ("id", "order", "amount", "payment_method", "transaction_id", "status", "timestamp")
    ordering = ("-timestamp",)

    @admin.display(description="Payment ID")
    def short_id(self, obj):
        return str(obj.id)[:8]

    @admin.display(description="Order")
    def order_link(self, obj):
        return obj.order.short_id if obj.order else "—"

    def has_add_permission(self, request):
        return False
