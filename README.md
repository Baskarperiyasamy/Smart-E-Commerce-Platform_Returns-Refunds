# Smart E-Commerce Platform — Catalog, Cart, Stripe Checkout, Notifications & Django Admin

FastAPI backend + plain HTML/CSS/JS frontend + Django Admin Panel, all backed by the same **MySQL** database.

```
smart-ecommerce-mysql/
├── fastapi_backend/    # Product/Cart/Checkout/Payment/Notification APIs (Python/FastAPI + MySQL)
├── admin_panel/         # Django Admin Panel — user/product/order management, analytics, CSV/PDF export
├── frontend/            # HTML/CSS/JS storefront (incl. Database Viewer, Orders, Notifications)
├── postman/             # Postman collection
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

**Checkout & Payments (new)**
- `POST /checkout/` — validates the cart, calculates the total, creates an
  `Order` (+ `OrderItem` line-item snapshots) and a `Payment` record, then
  creates a **Stripe Checkout Session** (which also creates the underlying
  Stripe **PaymentIntent**). Returns a `checkout_url` — redirect the browser
  there to pay.
- `POST /webhooks/stripe` — Stripe calls this after payment succeeds/fails.
  Flips `Order.payment_status` / `Order.order_status`, updates the `Payment`
  row, and decrements product stock once payment is confirmed.
- `GET /orders/` — the logged-in user's own orders (with items + payments)
- `GET /orders/{id}` — a single order (owner, or admin/staff)
- `GET /orders/all` — every order (admin/staff only)
- `PUT /orders/{id}/status` — move an order along `pending → paid → shipped →
  delivered` or `cancelled` (admin/staff only)

**Notifications & Real-Time Updates (new)**
- `GET /notifications/` — every notification for the logged-in user, newest first
- `POST /notifications/read` — mark one notification as read (pass
  `notification_id`), or all of them (omit it)
- `WS /ws/notifications?token=...` — WebSocket channel pushing
  `order_status_updated` and `cart_updated` events live to the browser
- A `Notification` row is created — and an email sent, and a WebSocket event
  pushed — automatically whenever: an order is placed (order confirmed), a
  Stripe payment succeeds or fails, or an order's status is set to `shipped`
  or `delivered`.

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

**Order** — `user`, `items` (products), `total_amount`, `payment_status`
(`pending`/`paid`/`failed`/`refunded`), `order_status`
(`pending`/`paid`/`shipped`/`delivered`/`return_requested`/`cancelled`), `created_at`.

**Payment** — `order_id`, `amount`, `payment_method`, `transaction_id`
(Stripe PaymentIntent id), `status`, `timestamp`.

**Notification** — `id`, `user`, `type` (`order_confirmed` / `payment_successful`
/ `payment_failed` / `order_shipped` / `order_delivered` / `order_return_requested`), `message`,
`read_status`, `timestamp`.

**Returns / Refunds — Customer Experience & Insights Module (new)**
- `POST /orders/{order_id}/return` — customer requests a return for one of
  their own orders. Body: `{"reason": "...", "comment": "optional"}`.
  Allowed only if `order_status == "delivered"` and it's within **7 days**
  of delivery; sets `order_status → "return_requested"` and creates a
  `ReturnRequest` (`status: pending`).
- `GET /orders/{order_id}/return` — fetch the return request (if any) for
  one order.
- `GET /orders/returns/all` — every return request (admin/staff only).
- Approving/rejecting a return is done from the **Django Admin panel**
  (`/admin/storefront/returnrequest/`), same as every other staff action
  that changes order status in this project. Approving sets
  `payment_status → refunded` and `order_status → cancelled`; rejecting
  sets `order_status` back to `delivered`. Both notify the customer.
- **Frontend**: `orders.html` shows a **Request Return** button on eligible
  orders (delivered, within the 7-day window, no existing return), and a
  status badge (`pending` / `approved` / `rejected`) once one's been
  submitted.

**ReturnRequest** — `id`, `order_id`, `user_id`, `reason`, `comment`,
`status` (`pending`/`approved`/`rejected`), `created_at`. One per order.

**Relationships** — `User → Cart → Product`, `User → Order → OrderItem →
Product`, `Order → Payment`, all via foreign keys. Every query filters by the
logged-in user's id, so each user only ever sees their own cart/orders.

**Auth** — register, login, refresh, me, JWT, bcrypt hashing, Auth0 social
login, RBAC (admin / staff / customer).

**Database Viewer** (`frontend/database.html`) — an admin-only page showing
live Users / Products / Cart tables.

**Django Admin Panel (new — `admin_panel/`)** — a separate Django project on
port 8001, sharing the exact same MySQL database as the FastAPI backend via
*unmanaged* models (Django never creates/alters these tables — SQLAlchemy
already owns that schema; Django only reads and writes rows):
- **User Management** — view/search users, edit details, assign roles
  (admin/staff/customer), activate/deactivate accounts (bulk actions)
- **Product Management** — add, edit, delete products; upload a product
  image (saved to `admin_panel/media/products/`, its URL appended to the
  product's `images` field); update stock directly from the list view
- **Order Management** — view every order with its line items and payment
  history inline; changing `order_status` to `shipped` or `delivered`
  automatically creates a `Notification` row and sends the customer an
  email, the same way the FastAPI webhook does
- **Analytics Dashboard** (`/dashboard/`) — Chart.js charts for total sales,
  a 30-day revenue trend, and top-selling products, plus a low-stock alert
  table
- **Export Reports** — Orders, Sales, and Users reports, each downloadable
  as CSV or PDF

One honest limitation: order-status changes made from the Django admin
**do** create the Notification row and send the email, but they **can't**
push the live WebSocket update — that connection lives inside the separate
FastAPI process's memory, which Django has no way to reach into. The
customer still sees the new notification the next time they load/refresh
`notifications.html`, just not instantly. Changes made through the FastAPI
API itself (e.g. `PUT /orders/{id}/status` in Swagger) still push live, as
before.

---

## MySQL Setup (do this first)

### 1. Create the database in MySQL Workbench

1. Open MySQL Workbench, connect to your local MySQL server
2. Open a new SQL tab and run:
   ```sql
   CREATE DATABASE ecommerce_db;
   ```
3. That's it — no tables to create manually. SQLAlchemy will create all
   tables automatically (including the new `orders`, `order_items`, and
   `payments` tables) the first time the FastAPI app starts.

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

### Set up Stripe (new)

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
   checkout locally; it's what forwards Stripe's payment-confirmation
   events to your backend.

### Set up Email Notifications (new)

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

Then create the tables and load sample data:
```bash
python seed_admin.py
python seed_products.py
uvicorn app.main:app --reload --port 8000
```

Confirm by going back to MySQL Workbench and running:
```sql
USE ecommerce_db;
SHOW TABLES;   -- now includes orders, order_items, payments
```

Swagger docs: **http://127.0.0.1:8000/docs**

---

## Frontend Setup

```bash
cd frontend
python -m http.server 5500
```

Open **http://127.0.0.1:5500/index.html**

---

## Django Admin Panel Setup (new)

**Do this only after the FastAPI backend has been started at least once**
(the `python seed_admin.py` / `uvicorn` steps above) — that's what actually
creates the `users`, `products`, `orders`, etc. tables in MySQL. Django
attaches to those existing tables; it doesn't create them.

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
This only creates Django's **own** internal tables (`auth_user`,
`django_session`, `django_admin_log`, etc.) — it will not touch `users`,
`products`, `orders`, or any other table the FastAPI backend owns.

Create your Django admin login (this is separate from the app's own
`admin@example.com` — it's specifically for logging into this Django panel):
```bash
python manage.py createsuperuser
```
Follow the prompts (username, email, password), then start the server:
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
5. Check `orders.html` for your order history, or MySQL Workbench:
   `SELECT * FROM orders; SELECT * FROM payments;`

If `payment_status` stays `pending` after paying, make sure the
`stripe listen --forward-to localhost:8000/webhooks/stripe` terminal is
still running — that's what delivers Stripe's confirmation to your backend.

---

## Try Notifications end-to-end

1. Log in as a customer in one browser tab, and open `notifications.html`
   — this opens a live WebSocket connection to the backend
2. In another tab (or the same one), place an order via Checkout
3. The moment the order is created, an **"Order confirmed"** notification
   appears instantly on the Notifications page (pushed over WebSocket, no
   refresh needed) — and an email goes out if SMTP is configured
4. Complete the Stripe payment — a **"Payment successful"** notification
   arrives the same way once the webhook confirms it
5. Log in as admin, open Swagger (`/docs`), and use
   `PUT /orders/{order_id}/status` with `"order_status": "shipped"`, then
   `"delivered"` — each one fires a live notification + email to the customer
6. Click **Mark all as read** on the Notifications page, or mark a single
   one — `POST /notifications/read`
7. To see the cart's real-time side: open `cart.html` in two tabs logged in
   as the same user, add an item in one tab, and watch the other tab's
   totals update automatically via the `cart_updated` WebSocket event

If notifications don't appear live, check the browser console for a
WebSocket connection error — the token is passed as
`?token=...` in the URL since browsers can't set custom headers on a
WebSocket handshake.

---

## Try the Django Admin Panel end-to-end

1. Go to `http://127.0.0.1:8001/admin/` and log in with your Django superuser
2. Click **Users** — search for a customer, edit their role or untick
   "Is active" to deactivate them, or use the bulk actions dropdown
   (Assign role: Admin/Staff/Customer, Activate/Deactivate) on multiple
   users at once
3. Click **Products** → **Add product** — fill in the fields and use the
   **Image upload** field at the bottom to attach a real image file; save,
   and the image's URL is appended to that product's `images` field
4. Click **Orders** — open any order to see its line items and payment
   history inline (read-only, since those come from checkout/Stripe).
   Change `order_status` to `Shipped`, save — the customer gets a new
   Notification row + an email (check their inbox if SMTP is configured)
5. Go to `http://127.0.0.1:8001/dashboard/` — see total sales, the revenue
   trend chart, top-selling products, and any low-stock products
6. Click any of the **Export Reports** links at the bottom of the dashboard
   to download the Orders/Sales/Users report as CSV or PDF

---

## Optional Docker Deployment

A `docker-compose.yml` at the project root containerizes MySQL + the
FastAPI backend + the Django Admin Panel (the frontend and Stripe CLI still
run locally, same as before — this only containerizes the two Python
services and their database):

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
your real Stripe/SMTP values before starting — `docker-compose.yml` doesn't
generate those for you, it only wires up the database connection.

---

## Postman

Import `postman/ecommerce_auth.postman_collection.json` — organized into
**Auth**, **Products**, **Cart**, **Checkout**, **Orders**, **Notifications**
folders, covering every FastAPI endpoint above. The Django Admin Panel is a
server-rendered, browser-based tool (not a JSON API), so it isn't part of
this collection — use a browser for it, as described above.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'stripe'` | Run `pip install -r requirements.txt` again — it's in there now |
| `Stripe error: ...` on `POST /checkout/` | Double-check `STRIPE_SECRET_KEY` in `.env` is a valid **test** key (starts `sk_test_`) |
| Order stays `payment_status: pending` after paying | The `stripe listen --forward-to localhost:8000/webhooks/stripe` terminal isn't running, or `STRIPE_WEBHOOK_SECRET` in `.env` doesn't match the one it printed |
| `Invalid webhook signature` in backend logs | `STRIPE_WEBHOOK_SECRET` doesn't match the current `stripe listen` session — restart `stripe listen` and copy the new `whsec_...` value |
| `AttributeError: 'get' is a dict method, but a Session is not a dict` | You're on an older copy of `webhooks.py` — this is fixed by calling `.to_dict()` on `event["data"]["object"]` before using `.get(...)` on it (newer `stripe` SDK versions no longer support dict-style `.get()` directly) |
| Notifications page shows nothing / WebSocket won't connect | Make sure you're logged in (the token is required as a query param) and that the backend is running on port 8000 |
| `[email] SMTP not configured — skipped ...` in backend/Django logs | Expected if you haven't filled in `SMTP_*` values in `.env` yet — notifications still get created, only the email is skipped |
| Email fails with an authentication error | For Gmail, you must use an **App Password**, not your normal account password, and 2-Step Verification must be turned on first |
| Django `django.db.utils.OperationalError` on startup | `admin_panel/.env` has the wrong MySQL credentials, or MySQL isn't running — double-check it matches `fastapi_backend/.env` |
| Django admin shows no Users/Products/Orders | You ran `python manage.py migrate` before ever starting the FastAPI backend, so those tables don't exist yet — start `uvicorn` at least once first (see "Django Admin Panel Setup" above) |
| Order status changed in Django doesn't update instantly in `notifications.html` | Expected — see the "one honest limitation" note under Django Admin Panel above; the Notification + email still get created, just not the live push |
| `Access denied for user 'root'@'localhost'` | Your password in `.env` is wrong — double-check it matches MySQL Workbench's connection |
| `Unknown database 'ecommerce_db'` | You skipped the `CREATE DATABASE ecommerce_db;` step in MySQL Workbench |
| `Can't connect to MySQL server` | MySQL server isn't running — start it (Workbench usually shows server status, or check Windows Services for "MySQL80" or similar) |
| Tables don't appear in Workbench | Make sure you ran `python seed_admin.py` at least once — that's what triggers table creation |
