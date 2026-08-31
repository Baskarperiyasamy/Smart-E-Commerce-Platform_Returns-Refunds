import csv
import io
import json
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from storefront.models import EcommerceUser, Order, OrderItem, Payment, Product


# ---------------------------------------------------------------------
# 4. Analytics Dashboard
# ---------------------------------------------------------------------

# Fixed colors so a given payment/order status always gets the same
# color across page loads (green = good, amber = waiting, red = bad).
PAYMENT_STATUS_COLORS = {
    "paid": "#22C55E",
    "pending": "#F59E0B",
    "failed": "#EF4444",
    "refunded": "#6366F1",
}
ORDER_STATUS_COLORS = {
    "pending": "#F59E0B",
    "paid": "#3B82F6",
    "shipped": "#8B5CF6",
    "delivered": "#22C55E",
    "return_requested": "#F97316",
    "cancelled": "#EF4444",
}


@staff_member_required
def dashboard(request):
    paid_orders = Order.objects.filter(payment_status="paid")

    total_sales = paid_orders.aggregate(total=Sum("total_amount"))["total"] or 0
    total_orders = Order.objects.count()
    total_paid_orders = paid_orders.count()
    avg_order_value = (total_sales / total_paid_orders) if total_paid_orders else 0

    low_stock_threshold = settings.LOW_STOCK_THRESHOLD

    # Revenue trend — last 30 days, paid orders only
    since = timezone.now() - timedelta(days=30)
    revenue_rows = (
        paid_orders.filter(created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total_amount"))
        .order_by("day")
    )
    revenue_labels = [row["day"].strftime("%b %d") for row in revenue_rows]
    revenue_values = [round(row["revenue"] or 0, 2) for row in revenue_rows]

    # Top-selling products — by units sold, paid orders only
    top_products_rows = (
        OrderItem.objects.filter(order__payment_status="paid")
        .values("product_name")
        .annotate(units_sold=Sum("quantity"))
        .order_by("-units_sold")[:5]
    )
    product_labels = [row["product_name"] for row in top_products_rows]
    product_values = [row["units_sold"] for row in top_products_rows]

    # --- Payment status breakdown (completed vs pending vs failed vs refunded) ---
    # Counted from the Payment ledger (one row per attempt) rather than Order,
    # since that's the true record of what Stripe/the payment flow reported.
    payment_status_rows = Payment.objects.values("status").annotate(count=Count("id"))
    payment_status_counts = {row["status"]: row["count"] for row in payment_status_rows}
    total_payments = sum(payment_status_counts.values())
    payment_status_labels = ["Paid", "Pending", "Failed", "Refunded"]
    payment_status_keys = ["paid", "pending", "failed", "refunded"]
    payment_status_values = [payment_status_counts.get(k, 0) for k in payment_status_keys]
    payment_status_colors = [PAYMENT_STATUS_COLORS[k] for k in payment_status_keys]
    completed_payments = payment_status_counts.get("paid", 0)
    incomplete_payments = total_payments - completed_payments

    # --- Order status breakdown ---
    order_status_rows = Order.objects.values("order_status").annotate(count=Count("id"))
    order_status_counts = {row["order_status"]: row["count"] for row in order_status_rows}
    order_status_keys = ["pending", "paid", "shipped", "delivered", "return_requested", "cancelled"]
    order_status_labels = [k.replace("_", " ").capitalize() for k in order_status_keys]
    order_status_values = [order_status_counts.get(k, 0) for k in order_status_keys]
    order_status_colors = [ORDER_STATUS_COLORS[k] for k in order_status_keys]

    # Low stock alerts
    low_stock_products = Product.objects.filter(stock__lt=low_stock_threshold).order_by("stock")

    context = {
        "total_sales": round(total_sales, 2),
        "total_orders": total_orders,
        "total_paid_orders": total_paid_orders,
        "avg_order_value": round(avg_order_value, 2),
        "low_stock_products": low_stock_products,
        "low_stock_threshold": low_stock_threshold,
        "low_stock_count": low_stock_products.count(),
        "generated_at": timezone.now(),
        "revenue_labels_json": json.dumps(revenue_labels),
        "revenue_values_json": json.dumps(revenue_values),
        "product_labels_json": json.dumps(product_labels),
        "product_values_json": json.dumps(product_values),
        "total_payments": total_payments,
        "completed_payments": completed_payments,
        "incomplete_payments": incomplete_payments,
        "payment_status_labels_json": json.dumps(payment_status_labels),
        "payment_status_values_json": json.dumps(payment_status_values),
        "payment_status_colors_json": json.dumps(payment_status_colors),
        "order_status_labels_json": json.dumps(order_status_labels),
        "order_status_values_json": json.dumps(order_status_values),
        "order_status_colors_json": json.dumps(order_status_colors),
        "order_status_counts": [
            {
                "label": label,
                "count": order_status_counts.get(key, 0),
                "key": key,
                "color": ORDER_STATUS_COLORS[key],
            }
            for label, key in zip(order_status_labels, order_status_keys)
        ],
    }
    return render(request, "storefront/dashboard.html", context)


# ---------------------------------------------------------------------
# 5. Export Reports — CSV and PDF, for Orders / Sales / Users
# ---------------------------------------------------------------------

def _csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def _pdf_response(filename, title, headers, rows):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    elements = [Paragraph(title, styles["Title"]), Spacer(1, 16)]

    table_data = [headers] + [[str(cell) for cell in row] for row in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222E3A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@staff_member_required
def export_orders(request, fmt):
    headers = ["Order ID", "Customer", "Email", "Total", "Order Status", "Payment Status", "Created At"]
    rows = [
        [
            o.short_id, o.user.name, o.user.email, f"${o.total_amount:.2f}",
            o.order_status, o.payment_status, o.created_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for o in Order.objects.select_related("user").all()
    ]
    if fmt == "csv":
        return _csv_response("orders_report.csv", headers, rows)
    return _pdf_response("orders_report.pdf", "Orders Report", headers, rows)


@staff_member_required
def export_sales(request, fmt):
    paid_orders = Order.objects.select_related("user").filter(payment_status="paid")
    headers = ["Order ID", "Customer", "Total", "Order Status", "Paid On"]
    rows = [
        [o.short_id, o.user.name, f"${o.total_amount:.2f}", o.order_status, o.updated_at.strftime("%Y-%m-%d %H:%M")]
        for o in paid_orders
    ]
    total_revenue = paid_orders.aggregate(total=Sum("total_amount"))["total"] or 0
    rows.append(["", "", "", "TOTAL REVENUE", f"${total_revenue:.2f}"])

    if fmt == "csv":
        return _csv_response("sales_report.csv", headers, rows)
    return _pdf_response("sales_report.pdf", "Sales Report", headers, rows)


@staff_member_required
def export_users(request, fmt):
    headers = ["Name", "Email", "Role", "Active", "Provider", "Joined"]
    rows = [
        [u.name, u.email, u.role, "Yes" if u.is_active else "No", u.auth_provider, u.created_at.strftime("%Y-%m-%d")]
        for u in EcommerceUser.objects.all()
    ]
    if fmt == "csv":
        return _csv_response("users_report.csv", headers, rows)
    return _pdf_response("users_report.pdf", "Users Report", headers, rows)
