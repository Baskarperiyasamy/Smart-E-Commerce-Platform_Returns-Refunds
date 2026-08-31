# SmartCart Admin Panel (Django)

This is the internal staff admin panel for the SmartCart e-commerce platform.
It connects to the **same MySQL database** your FastAPI backend already uses
(`ecommerce_db`) — Django's own auth/session tables are created fresh here,
but the e-commerce tables (users, products, orders, order_items, payments,
cart, notifications, return_requests) are mapped as **unmanaged** models, so
Django only reads and writes rows; it never touches the schema
FastAPI/SQLAlchemy owns.

## What's included

| Requirement | Where |
|---|---|
| 1. User Management | `/admin/storefront/ecommerceuser/` — view, edit, assign role (admin/staff/customer), activate/deactivate |
| 2. Product Management | `/admin/storefront/product/` — add/edit/delete, image upload field, inline stock editing |
| 3. Order Management | `/admin/storefront/order/` — view all orders, update order/payment status, mark shipped/delivered/cancelled (auto-notifies the customer via `Notification` row + email, same as the FastAPI flow) |
| 4. Analytics Dashboard | `/dashboard/` — total sales, total orders, avg order value, low stock count, revenue trend (line), **payment status breakdown: completed vs. pending vs. failed vs. refunded** (doughnut), top-selling products (bar), order status breakdown (bar, now includes Return Requested), low stock table |
| 5. Export Reports | CSV + PDF buttons on the dashboard, or directly: `/reports/orders.csv`, `/reports/orders.pdf`, `/reports/sales.csv`, `/reports/sales.pdf`, `/reports/users.csv`, `/reports/users.pdf` |
| 6. **Return Requests (Day 5 — new)** | `/admin/storefront/returnrequest/` — every return a customer submitted via `POST /orders/{order_id}/return`. Select rows and use **Approve selected returns** (refunds the order: `payment_status → refunded`, `order_status → cancelled`) or **Reject selected returns** (`order_status → delivered`). Both notify the customer the same way OrderAdmin's shipped/delivered actions do. |
| Bonus: Payments list | `/admin/storefront/payment/` — every payment attempt, filterable by status, so you can see completed vs. not-completed at a glance without opening each order |

Charts are built with **Chart.js** (loaded from CDN, no extra install needed).

## ⚠️ Before you share/submit this project

Your original `.env` had **real credentials** in it (a MySQL password and a
working Gmail app password). Do this now:

1. Only ever commit/zip `.env.example` (placeholders) — never the real `.env`.
2. Revoke that Gmail app password (Google Account → Security → App Passwords)
   and generate a new one, then update your local `.env` files.
3. Confirm `.gitignore` actually lists `.env`, not just `.env.example`.

## Setup

```bash
cd admin_panel
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

copy .env.example .env         # Windows: copy | macOS/Linux: cp
# then edit .env with your real DB_PASSWORD / SMTP values
# (use the SAME ecommerce_db + SMTP values as fastapi_backend/.env)

python manage.py migrate       # creates Django's own auth/session tables only
python manage.py createsuperuser
python manage.py runserver 8001
```

Then visit:
- `http://127.0.0.1:8001/admin/` — the admin panel (Users, Products, Orders, Return Requests, Payments, Carts, Notifications)
- `http://127.0.0.1:8001/dashboard/` — the analytics dashboard (log in first — it requires staff access)

## Notes

- **Timezone**: `USE_TZ = False` on purpose — the FastAPI backend stores naive UTC timestamps (`datetime.utcnow()`), so Django is kept naive too to avoid mismatches on the shared columns.
- **Low stock threshold**: configurable via `LOW_STOCK_THRESHOLD` in `.env` (default 10). Used consistently by both the product list badge and the dashboard.
- **Real-time limitation**: changing an order's status here creates the `Notification` row and sends the email, exactly like the FastAPI flow — but it can't push a live WebSocket event, because that connection lives in the separate FastAPI process's memory. The customer sees the update on their next page load instead of instantly.
- **Payment status "completed" vs. "not completed"**: the dashboard counts every row in the `Payment` table (one row per attempt, as recorded by your payment flow) and buckets `paid` as completed; `pending` + `failed` + `refunded` as not completed.
- **Return window**: the 7-day return window is enforced by the FastAPI backend (`app/routers/returns.py`), not here — this admin only reviews return requests that already passed that check.
