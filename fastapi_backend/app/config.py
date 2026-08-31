from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./ecommerce.db"

    secret_key: str = "insecure_dev_secret_change_me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    auth0_domain: str = ""  
    auth0_client_id: str = ""
    auth0_client_secret: str = ""
    auth0_audience: str = ""
    auth0_algorithms: str = "RS256"

    # Day 2: cart tax calculation. 0.08 = 8%. Set to 0 to disable tax entirely.
    tax_rate: float = 0.08

    # Day 3: Stripe checkout + payments
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_currency: str = "usd"

    # Where Stripe Checkout redirects after payment succeeds / is cancelled.
    # Point these at your frontend (served on 5500 by `python -m http.server 5500`).
    checkout_success_url: str = "http://127.0.0.1:5500/frontend/order-success.html?session_id={CHECKOUT_SESSION_ID}"
    checkout_cancel_url: str = "http://127.0.0.1:5500/frontend/cart.html"

    # Day 4: Email notifications via SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_from_name: str = "SmartCart"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
