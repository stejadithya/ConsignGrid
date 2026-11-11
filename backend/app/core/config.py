"""Application configuration, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "staging" behaves like production (strong secret required); the pilot runs as "staging".
    app_env: Literal["development", "test", "staging", "production"] = "development"
    # Branding: display only. Never used in identifiers, table names or API paths.
    app_display_name: str = "TyreGrow"

    database_url: str = "postgresql+psycopg://tyreworld:tyreworld@localhost:5432/tyreworld"
    # Serverless hosts (e.g. Vercel functions): open a connection per request instead of keeping a pool.
    db_disable_pool: bool = False
    # Set when connecting through a transaction-mode pooler (PgBouncer) that cannot hold prepared statements.
    db_disable_prepared_statements: bool = False

    jwt_secret: str = DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60
    auth_cookie_name: str = "session"
    auth_cookie_secure: bool = False
    login_max_attempts: int = 5          # wrong passwords in a row before the account is locked
    login_lock_minutes: int = 15         # how long the lock lasts (an RM or Administrator can unlock sooner)
    password_history: int = 3            # a new password can't match the current one or the ones before it (3 in all)

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Business policy (see docs/DECISION_LOG.md)
    default_currency: str = "AUD"
    auto_allocate_on_create: bool = True
    allocation_policy: Literal["PRIORITY_THEN_OLDEST"] = "PRIORITY_THEN_OLDEST"
    invoice_due_days_default: int = 30
    # Consignment stock requests: configured limits (docs/STOCK_REQUESTS.md).
    stock_request_max_lines: int = 50
    stock_request_max_line_qty: int = 500
    # Delivery notes (PDF + email). Email is sent only when SMTP_HOST is set; otherwise the PDF can be downloaded.
    business_timezone: str = "Pacific/Auckland"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""            # e.g. "TyreGrow <deliveries@example.com>"
    smtp_starttls: bool = True
    delivery_note_reply_to: str = ""
    delivery_discrepancy_days: int = 14
    # Shared secret Vercel Cron sends (Authorization: Bearer ...) to run the daily photo clean-up.
    cron_secret: str = ""
    # Website stock API: warehouse available stock at or below this (and above 0) is reported as LOW. Same default as
    # the "Low" chip on the Warehouse screen.
    partner_low_stock_threshold: int = Field(default=4, ge=0)
    # Stock checks: hours the reseller has to confirm shortages, then how often reminders repeat (P-018).
    stocktake_confirm_hours: int = 48   # still accepted; new checks use STOCKTAKE_FIND_DAYS (release 1.11)
    stocktake_find_days: int = 5        # D3: days to find tyres not found at a stock check before they are invoiced
    stock_check_every_days: int = 30      # a dealer shop is due a stock check this many days after its last count
    stock_check_move_days: int = 14       # how far ahead a due stock check can be moved
    initial_stock_correction_days: int = 30   # days the RM may correct a dealer's initial stock (until the first stock check)
    stocktake_reminder_hours: int = 24
    # Issuer details printed on invoices (the dealership's legal entity).
    invoice_issuer_name: str = "TyreGrow"
    invoice_issuer_details: str = ""
    # Directory holding this deployment's reference documents and their manifest.json (empty = the bundled,
    # empty app/assets/reference). See app/modules/pilot/reference.py.
    reference_documents_dir: str = ""

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        """Accept provider-style URLs (postgres://, postgresql://) and use the psycopg 3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.app_env in ("staging", "production") and (self.jwt_secret == DEV_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("JWT_SECRET must be a strong secret (32+ characters) in staging and production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
