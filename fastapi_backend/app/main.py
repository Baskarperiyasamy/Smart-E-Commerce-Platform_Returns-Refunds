from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app import models  # noqa: F401  (import so tables are registered on Base)
from app import ws_manager
from app.routers import auth, products, cart, checkout, orders, returns, admin_returns, webhooks, notifications, ws

# Creates SQLite tables automatically on first run.
# For a production DB (Postgres/MySQL), swap DATABASE_URL in .env and use
# Alembic migrations instead of create_all.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart E-Commerce Platform - FastAPI Backend",
    description="User APIs, cart, orders, Stripe payments, real-time notifications, and "
                 "returns/refunds (Day 1: auth + RBAC | Day 2: catalog + cart | Day 3: checkout + "
                 "payments | Day 4: notifications, email, WebSockets | Day 5: Customer Experience "
                 "& Insights Module — return/refund requests | Day 6: admin-side refund processing, "
                 "inventory restock, Stripe refunds)",
    version="0.6.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def capture_event_loop():
    """Stores a reference to the running event loop so that regular (sync)
    request handlers — which FastAPI runs in a worker thread — can still
    schedule WebSocket broadcasts back onto it. See app/ws_manager.py."""
    import asyncio
    ws_manager.main_loop = asyncio.get_event_loop()


app.include_router(auth.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(checkout.router)
app.include_router(orders.router)
app.include_router(returns.router)
app.include_router(admin_returns.router)
app.include_router(webhooks.router)
app.include_router(notifications.router)
app.include_router(ws.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "fastapi_backend", "docs": "/docs"}