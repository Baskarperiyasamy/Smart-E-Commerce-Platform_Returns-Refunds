# Smart E-Commerce Platform — Catalog, Cart, Stripe Checkout, Notifications, Returns & Admin Refund Processing

FastAPI backend + plain HTML/CSS/JS frontend + Django Admin Panel, all backed by the same **MySQL** database.

```
smart-ecommerce-mysql/
├── fastapi_backend/    # Product/Cart/Checkout/Payment/Notification/Returns APIs (Python/FastAPI + MySQL)
├── admin_panel/         # Django Admin Panel — user/product/order/return management, analytics, CSV/PDF export
├── frontend/            # HTML/CSS/JS storefront (incl. Database Viewer, Orders, Notifications, Admin Returns)
├── postman/             # Postman collection
├── output_images/       # Screenshots demonstrating each module end-to-end
└── docker-compose.yml   # Optional Docker deployment (MySQL + both backends)
```

---

## What's inside

**Product APIs**
- `GET /products/` — filters: `category`, `min_price`, `max_price`, `in_stock`, `sort_by` (`price`/`popularity`/`name`), `order`
- `GET /products/category/{category}` — same filters, scoped to one category
- `GET /products/{id}`

**Cart APIs** — every response includes automatic calculations
- `POST /cart/add`
- `PUT /cart/update`
- `DELETE /cart/remove`
- `GET /cart`

**Checkout & Payments**
- `POST /checkout/` — validates the cart, calculates the total, creates an
  `Order` (+ `OrderItem` line-item snapshots) and a `Payment` record, then
  creates a **Stripe Checkout Session** (which also creates the underlying
  Stripe **PaymentIntent**). Returns a `checkout_url` — redirect the browser
  there to pay.
- `POST /webhooks/stripe` — Stripe calls this after payment succeeds/fails.
  Flips `Order.payment_status` / `Order.order_status`, updates the `Payment`
  row, and decrements product stock once payment is confirmed.
- `GET /orders/` — the logged-in user's own orders (with items + payments +
  tracking dates + any return request)
- `GET /orders/{id}` — a single order (owner, or admin/staff)
- `GET /orders/all` — every order (admin/staff only)
- `PUT /orders/{id}/status` — move an order along `pending → paid → shipped →
  delivered` or `cancelled` (admin/staff only). Recording `shipped` or
  `delivered` also stamps `Order.shipped_at` / `Order.delivered_at`.

**Notifications & Real-Time Updates**
- `GET /notifications/` — every notification for the logged-in user, newest first
- `POST /notifications/read` — mark one notification as read (pass
  `notification_id`), or all of them (omit it)
- `WS /ws/notifications?token=...` — WebSocket channel pushing
  `order_status_updated` and `cart_updated` events live to the browser
- A `Notification` row is created — and an email sent, and a WebSocket event
  pushed — automatically whenever: an order is placed, a Stripe payment
  succeeds or fails, an order's status is set to `shipped`/`delivered`, a
  return is approved/rejected, or a refund completes.

Each cart/checkout response includes:
```json
{
  "items": [ { "product_name": "...", "unit_price": 19.99, "quantity": 2, "item_total": 39.98 } ],
  "cart_total": 39.98,
  "tax_rate": 0.08,
  "tax": 3.20,
  "grand_total": 43.18
}
```

**Order** — `user`, `items` (products), `payments`, `total_amount`,
`payment_status` (`pending`/`paid`/`failed`/`refunded`), `order_status`
(`pending`/`paid`/`shipped`/`delivered`/`return_requested`/`returned`/`cancelled`),
`created_at`, `updated_at`, `shipped_at`, `delivered_at`.

**Payment** — `order_id`, `amount`, `payment_method`, `transaction_id`
(Stripe PaymentIntent/Refund id), `status`, `timestamp`.

**Notification** — `id`, `user`, `type` (`order_confirmed` / `payment_successful`
/ `payment_failed` / `order_shipped` / `order_delivered` / `order_return_requested`
/ `return_approved` / `return_rejected` / `refund_completed`), `message`,
`read_status`, `timestamp`.

---

## Returns & Refunds (Customer + Admin)

### Customer side
- `POST /orders/{order_id}/return` — customer requests a return for one of
  their own orders. Body: `{"reason": "...", "comment": "optional"}`.
  Allowed only if `order_status == "delivered"` and it's within **7 days**
  of delivery; sets `order_status → "return_requested"` and creates a
  `ReturnRequest` (`status: pending`).
- `GET /orders/{order_id}/return` — fetch the return request (if any) for
  one order.
- **Frontend**: `orders.html` shows a **Request Return** button on eligible
  orders (delivered, within the 7-day window, no existing return), a
  status chip (`pending`/`approved`/`rejected`) once one's been submitted,
  and a collapsible **View Order Details** panel.

### Admin side — return/refund processing
Full lifecycle control lives in FastAPI, exposed to staff through a
dedicated frontend page:

- `GET /admin/returns/` — every return request, newest first, with the
  full order embedded (items, totals, `shipped_at`/`delivered_at` tracking
  dates) so the admin UI needs only this one call.
- `POST /admin/returns/{return_id}/approve` — optional body
  `{"admin_note": "..."}`. Sets `ReturnRequest.status → approved`,
  `Order.order_status → returned`, **restocks inventory** (adds each line
  item's quantity back to `Product.stock`), issues a **Stripe refund**
  (`stripe.Refund.create`) when a real payment intent exists, and sets
  `Order.payment_status → refunded`. Sends two notifications in sequence:
  `return_approved`, then `refund_completed`.
- `POST /admin/returns/{return_id}/reject` — optional body
  `{"admin_note": "..."}`. Sets `ReturnRequest.status → rejected`,
  `Order.order_status` back to `delivered`. Sends a `return_rejected`
  notification including the admin's note as the reason.
- **Frontend**: `frontend/admin-returns.html` — admin/staff-only page with:
  - Live stats cards (Pending / Approved / Rejected / Total Refunded),
    auto-refreshing every 15 seconds
  - Searchable, filterable table of every return request
  - A detail modal per order showing full tracking (`Created` /
    `Shipped` / `Delivered` timestamps), items, and the return reason —
    with **Approve Return** / **Reject Return** actions (rejecting
    requires a note, which is sent to the customer)

**ReturnRequest** — `id`, `order_id`, `user_id`, `reason`, `comment`,
`admin_note`, `status` (`pending`/`approved`/`rejected`), `created_at`.
One per order.

**Relationships** — `User → Cart → Product`, `User → Order → OrderItem →
Product`, `Order → Payment`, `Order → ReturnRequest`, all via foreign keys.
Every query filters by the logged-in user's id, so each user only ever sees
their own cart/orders (admins/staff can see all).

---

**Auth** — register, login, refresh, me, JWT, bcrypt hashing, Auth0 social
login, RBAC (admin / staff / customer).

**Database Viewer** (`frontend/database.html`) — an admin-only page showing
live Users / Products / Cart tables.

**Django Admin Panel (`admin_panel/`)** — a separate Django project on
port 8001, sharing the exact same MySQL database as the FastAPI backend via
*unmanaged* models (Django never creates/alters these tables — SQLAlchemy
already owns that schema; Django only reads and writes rows):
- **User Management** — view/search users, edit details, assign roles
  (admin/staff/customer), activate/deactivate accounts (bulk actions)
- **Product Management** — add, edit, delete products; upload a product
  image; update stock directly from the list view
- **Order Management** — view every order with its line items and payment
  history inline; changing `order_status` to `shipped` or `delivered`
  automatically creates a `Notification` row and sends the customer an
  email, the same way the FastAPI webhook does
- **Return Requests** — read-only view of all `ReturnRequest` rows for
  reference/search. **Approving/rejecting returns for real is done through
  the FastAPI admin endpoints above (via `admin-returns.html` or Swagger)**,
  since that's the single source of truth for the restock + Stripe refund
  logic — the Django side isn't kept in sync with that workflow.
- **Analytics Dashboard** (`/dashboard/`) — Chart.js charts for total sales,
  a 30-day revenue trend, order status breakdown (including
  `return_requested`), top-selling products, and a low-stock alert table
- **Export Reports** — Orders, Sales, and Users reports, each downloadable
  as CSV or PDF

One honest limitation: order-status/return changes made from the Django
admin **do** create the Notification row and send the email, but they
**can't** push the live WebSocket update — that connection lives inside the
separate FastAPI process's memory, which Django has no way to reach into.
The customer still sees the new notification the next time they
load/refresh `notifications.html`, just not instantly. Changes made through
the FastAPI API (Swagger, or `admin-returns.html`) still push live.

---

## MySQL Setup (do this first)

### 1. Create the database in MySQL Workbench

1. Open MySQL Workbench, connect to your local MySQL server
2. Open a new SQL tab and run:
   ```sql
   CREATE DATABASE ecommerce_db;
   ```
3. SQLAlchemy creates the core tables automatically the first time the
   FastAPI app starts. Two additional migrations are needed for the
   returns/refunds module (see "Returns/Refunds schema" below).

### 2. Confirm your MySQL credentials

You'll need: host (usually `localhost`), port (usually `3306`), username
(often `root`), and your MySQL password.

---

## Backend Setup

```bash
cd fastapi_backend

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

Open `.env` and edit:
```
DATABASE_URL=mysql+pymysql://root:your_mysql_password@localhost:3306/ecommerce_db
```

### Set up Stripe

1. Create a free account at https://dashboard.stripe.com/register
2. Go to **Developers → API keys** and copy your **test** Secret key and
   Publishable key into `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   ```
3. Install the [Stripe CLI](https://docs.stripe.com/stripe-cli) and run,
   in a separate terminal, while your backend is running:
   ```bash
   stripe login
   stripe listen --forward-to localhost:8000/webhooks/stripe
   ```
   This prints a `whsec_...` value — paste it into `.env` as
   `STRIPE_WEBHOOK_SECRET`. Keep this terminal running any time you test
   checkout, or an admin return approval (which also calls Stripe), locally.

### Set up Email Notifications

Notifications are sent via SMTP. Easiest option — a Gmail account:

1. Turn on 2-Step Verification on your Google account (required for the next step)
2. Generate an "App Password" at https://myaccount.google.com/apppasswords
3. In `.env`, set:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_16_character_app_password
   EMAIL_FROM=your_email@gmail.com
   ```

If SMTP isn't configured, the app still works — it just logs
`[email] SMTP not configured — skipped '...'` to the terminal instead of
sending, so the Notification row and the WebSocket push still happen either way.

Then create the tables:
```bash
uvicorn app.main:app --reload --port 8000
```

### Returns/Refunds schema (one-time, run in MySQL Workbench)

`create_all()` only creates brand-new tables — it won't alter existing
`ENUM` columns or add new columns to `orders`/`return_requests` created in
earlier sessions. Run this once against `ecommerce_db`:

```sql
USE ecommerce_db;

ALTER TABLE orders
  MODIFY order_status ENUM('pending','paid','shipped','delivered','return_requested','returned','cancelled') NOT NULL DEFAULT 'pending',
  ADD COLUMN shipped_at DATETIME NULL AFTER updated_at,
  ADD COLUMN delivered_at DATETIME NULL AFTER shipped_at;

ALTER TABLE notifications
  MODIFY type ENUM('order_confirmed','payment_successful','payment_failed','order_shipped','order_delivered','order_return_requested','return_approved','return_rejected','refund_completed') NOT NULL;

ALTER TABLE return_requests
  ADD COLUMN admin_note TEXT NULL AFTER comment;
```

Confirm by going back to MySQL Workbench and running:
```sql
SHOW TABLES;   -- includes orders, order_items, payments, return_requests
SHOW COLUMNS FROM orders LIKE 'shipped_at';
SHOW COLUMNS FROM return_requests LIKE 'admin_note';
```

Swagger docs: **http://127.0.0.1:8000/docs**

---

## Frontend Setup

```bash
cd frontend
python -m http.server 5500
```

Open **http://127.0.0.1:5500/index.html**

Admin/staff accounts land on **http://127.0.0.1:5500/admin-returns.html**
after login; everyone else lands on `products.html`.

---

## Django Admin Panel Setup

**Do this only after the FastAPI backend has been started at least once** —
that's what actually creates the `users`, `products`, `orders`, etc. tables
in MySQL. Django attaches to those existing tables; it doesn't create them.

```bash
cd admin_panel

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

Open `.env` and set the **same** MySQL credentials as `fastapi_backend/.env`
(same `ecommerce_db` database), and — optionally — the same `SMTP_*` values
so order-status emails sent from here work too:
```
DB_NAME=ecommerce_db
DB_USER=root
DB_PASSWORD=your_mysql_password
```

Then:
```bash
python manage.py migrate
```
This only creates Django's **own** internal tables — it will not touch
`users`, `products`, `orders`, `return_requests`, or any other table the
FastAPI backend owns.

Create your Django admin login (separate from the app's own JWT accounts):
```bash
python manage.py createsuperuser
```
Follow the prompts, then start the server:
```bash
python manage.py runserver 8001
```

Open **http://127.0.0.1:8001/admin/** and log in with the superuser you just
created. Analytics dashboard: **http://127.0.0.1:8001/dashboard/**

---

## Try Checkout end-to-end

1. Register/login as a customer, add a few products to your cart
2. Open `cart.html` and click **Checkout with Stripe**
3. You're redirected to Stripe's hosted checkout page — pay with the test
   card `4242 4242 4242 4242`, any future expiry date, any CVC, any ZIP
4. Stripe redirects you back to `order-success.html`, and (via the webhook,
   forwarded by `stripe listen`) your order's `payment_status` flips to
   `paid` and product stock is decremented

---

## Try Returns & Admin Refund Processing end-to-end

1. As admin/staff, mark a delivered order (`PUT /orders/{id}/status` with
   `"delivered"`, or via Django's "Mark selected orders as Delivered"
   action) — this stamps `delivered_at`
2. Log in as that order's customer, go to `orders.html` — a **Request
   Return** button appears since it's within the 7-day window
3. Submit a return with a reason — the order flips to `Return Requested`,
   the customer gets an in-app notification + email
4. Log in as admin, go to `admin-returns.html` — the new request appears
   in the table and in the **Pending** stat card
5. Open it, optionally add a note, click **Approve Return** — inventory is
   restocked, a Stripe refund is issued (if configured), `order_status`
   becomes `Returned`, `payment_status` becomes `Refunded`, and the
   customer receives two notifications (`Return Approved`, then
   `Refund Completed`) plus matching emails
6. Or click **Reject Return** (a note is required) — the order reverts to
   `Delivered`, and the customer gets a `Return Rejected` notification +
   email with your note as the reason

---

## Try Notifications end-to-end

1. Log in as a customer in one browser tab, and open `notifications.html`
   — this opens a live WebSocket connection to the backend
2. Place an order via Checkout — an **"Order confirmed"** notification
   appears instantly (pushed over WebSocket) and an email goes out if SMTP
   is configured
3. Complete the Stripe payment — a **"Payment successful"** notification
   arrives the same way
4. As admin, use `PUT /orders/{order_id}/status` with `"shipped"`, then
   `"delivered"` — each fires a live notification + email
5. Approve or reject a return as above — same live behavior
6. Click **Mark all as read**, or mark a single one — `POST /notifications/read`

---

## Try the Django Admin Panel end-to-end

1. Go to `http://127.0.0.1:8001/admin/` and log in with your Django superuser
2. **Users** — search for a customer, edit their role, or use bulk actions
   (Assign role, Activate/Deactivate)
3. **Products** — add a product with an image upload; edit stock inline
4. **Orders** — open any order to see items/payments inline; change
   `order_status` to `Shipped`/`Delivered` — triggers a Notification + email
5. **Return Requests** — browse submitted returns (read-only reference;
   approve/reject via the FastAPI endpoints/`admin-returns.html` instead)
6. `http://127.0.0.1:8001/dashboard/` — sales totals, revenue trend, order
   status breakdown, top products, low-stock alerts, CSV/PDF exports

---

## Optional Docker Deployment

A `docker-compose.yml` at the project root containerizes MySQL + the
FastAPI backend + the Django Admin Panel:

```bash
docker compose up --build
```

Then, once, in a separate terminal:
```bash
docker compose exec admin_panel python manage.py migrate
docker compose exec admin_panel python manage.py createsuperuser
```

- FastAPI: `http://localhost:8000/docs`
- Django Admin: `http://localhost:8001/admin/`

You still need `fastapi_backend/.env` and `admin_panel/.env` filled in with
your real Stripe/SMTP values, and the returns/refunds `ALTER TABLE`
statements applied, before starting.

---

## Postman

Import `postman/ecommerce_auth.postman_collection.json` — organized into
**Auth**, **Products**, **Cart**, **Checkout**, **Orders**, **Returns**,
**Admin Returns**, **Notifications** folders, covering every FastAPI
endpoint above. The Django Admin Panel is a server-rendered, browser-based
tool (not a JSON API), so it isn't part of this collection.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'stripe'` | Run `pip install -r requirements.txt` again |
| `Stripe error: ...` on `POST /checkout/` or approving a return | Double-check `STRIPE_SECRET_KEY` in `.env` is a valid **test** key (`sk_test_...`) |
| Order stays `payment_status: pending` after paying | The `stripe listen` terminal isn't running, or `STRIPE_WEBHOOK_SECRET` doesn't match |
| `sqlalchemy.exc.DataError: Data truncated for column 'order_status'` | You haven't run the returns/refunds `ALTER TABLE` migration yet — see "Returns/Refunds schema" above |
| `(1146, "Table 'ecommerce_db.return_requests' doesn't exist")` | Same — run the schema migration section above |
| `AttributeError: module 'bcrypt' has no attribute '__about__'` on register/login | `bcrypt`/`passlib` version mismatch — run `pip install "bcrypt==4.0.1"` and restart `uvicorn` |
| `ResponseValidationError` on `GET /notifications/` (`timestamp` is `None`) | A notification was created without a timestamp (usually from an older Django code path) — run `UPDATE notifications SET timestamp = NOW() WHERE timestamp IS NULL;`, and make sure `storefront/notifications.py` sets `timestamp=timezone.now()` explicitly |
| Notifications page shows nothing / WebSocket won't connect | Make sure you're logged in and the backend is running on port 8000 |
| `[email] SMTP not configured — skipped ...` | Expected if `SMTP_*` isn't filled in — notifications still get created, only the email is skipped |
| Django `django.db.utils.OperationalError` on startup | `admin_panel/.env` has the wrong MySQL credentials, or MySQL isn't running |
| Django admin shows no Users/Products/Orders | Start `uvicorn` at least once before running Django's `migrate` |
| Order status changed in Django doesn't update instantly in `notifications.html` | Expected — see the "one honest limitation" note above |
| `admin-returns.html` shows "AdminReturnsAPI is not defined" | `js/api.js` is missing the `AdminReturnsAPI` block — re-add it, save, and hard-refresh (Ctrl+F5) |
| 404 on pages you know exist | Check whether your static server is running from inside `frontend/` (URLs have no `/frontend/` prefix) or from the project root (URLs need it) — match the URL to how `python -m http.server` was started |
| Google/Auth0 login shows `invalid_request: couldn't find your session` | Stale Auth0 session cookie from overlapping login attempts — clear cookies for `*.auth0.com`, close all app tabs, and retry once in a fresh tab. This is a session-hygiene issue, unrelated to the API/backend |
| `Access denied for user 'root'@'localhost'` | Your password in `.env` is wrong |
| `Unknown database 'ecommerce_db'` | You skipped the `CREATE DATABASE ecommerce_db;` step |
| `Can't connect to MySQL server` | MySQL server isn't running |
