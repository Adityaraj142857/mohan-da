"""Configuration via .env (SPEC section 5). Fails loudly if required secrets
are missing or left at obvious placeholders once the owner tries to `run`
against a real channel; the demo (CHANNEL=simulator) works with defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

PLACEHOLDER_MARKERS = {"yourname@bank", "shop owner name", "changeme", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    shop_name: str = Field(default="My Shop", alias="SHOP_NAME")
    tz: str = Field(default="Asia/Kolkata", alias="TZ")

    upi_vpa: str = Field(default="yourname@bank", alias="UPI_VPA")
    payee_name: str = Field(default="SHOP OWNER NAME", alias="PAYEE_NAME")
    payee_name_aliases: str = Field(default="", alias="PAYEE_NAME_ALIASES")
    delivery_fee_paise: int = Field(default=1500, alias="DELIVERY_FEE_PAISE")
    hostels: str = Field(default="Hostel A,Hostel B", alias="HOSTELS")
    open_hours: str = Field(default="09:00-22:00", alias="OPEN_HOURS")
    payment_ttl_min: int = Field(default=15, alias="PAYMENT_TTL_MIN")
    late_credit_grace_min: int = Field(default=30, alias="LATE_CREDIT_GRACE_MIN")

    unique_amount_mode: str = Field(default="discount", alias="UNIQUE_AMOUNT_MODE")
    unique_paise_max: int = Field(default=30, alias="UNIQUE_PAISE_MAX")

    bank_signal: str = Field(default="sms", alias="BANK_SIGNAL")
    bank_sms_senders: str = Field(default=".*", alias="BANK_SMS_SENDERS")
    sms_webhook_secret: str = Field(default="dev-secret-change-me", alias="SMS_WEBHOOK_SECRET")
    pending_bank_timeout_min: int = Field(default=10, alias="PENDING_BANK_TIMEOUT_MIN")

    screenshot_policy: str = Field(default="owner_confirm", alias="SCREENSHOT_POLICY")
    auto_accept_overpay_paise: int = Field(default=0, alias="AUTO_ACCEPT_OVERPAY_PAISE")
    auto_approve_max_paise: int = Field(default=15000, alias="AUTO_APPROVE_MAX_PAISE")
    ocr_engine: str = Field(default="fake", alias="OCR_ENGINE")

    nlu_mode: str = Field(default="rules", alias="NLU_MODE")

    channel: str = Field(default="simulator", alias="CHANNEL")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    admin_password: str = Field(default="dev-admin-change-me", alias="ADMIN_PASSWORD")
    admin_secret_key: str = Field(default="dev-session-secret-change-me", alias="ADMIN_SECRET_KEY")
    bind_host: str = Field(default="127.0.0.1", alias="BIND_HOST")
    port: int = Field(default=8000, alias="PORT")

    owner_notify: str = Field(default="console", alias="OWNER_NOTIFY")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    whatsapp_token: str = Field(default="", alias="WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str = Field(default="", alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_verify_token: str = Field(default="", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str = Field(default="", alias="WHATSAPP_APP_SECRET")
    whatsapp_api_version: str = Field(default="", alias="WHATSAPP_API_VERSION")

    media_retention_days: int = Field(default=30, alias="MEDIA_RETENTION_DAYS")
    message_free_allowance: int = Field(default=1000, alias="MESSAGE_FREE_ALLOWANCE")

    db_path: str = Field(default="shopbot.db", alias="DB_PATH")
    debug: bool = Field(default=False, alias="DEBUG")

    @field_validator("unique_amount_mode")
    @classmethod
    def _check_unique_mode(cls, v: str) -> str:
        if v not in {"off", "discount", "surcharge"}:
            raise ValueError("UNIQUE_AMOUNT_MODE must be off|discount|surcharge")
        return v

    @field_validator("bank_signal")
    @classmethod
    def _check_bank_signal(cls, v: str) -> str:
        if v not in {"sms", "none"}:
            raise ValueError("BANK_SIGNAL must be sms|none")
        return v

    @field_validator("screenshot_policy")
    @classmethod
    def _check_screenshot_policy(cls, v: str) -> str:
        if v not in {"owner_confirm", "auto_approve_if_strong"}:
            raise ValueError("SCREENSHOT_POLICY must be owner_confirm|auto_approve_if_strong")
        return v

    @field_validator("channel")
    @classmethod
    def _check_channel(cls, v: str) -> str:
        if v not in {"simulator", "whatsapp"}:
            raise ValueError("CHANNEL must be simulator|whatsapp")
        return v

    def hostel_list(self) -> list[str]:
        return [h.strip() for h in self.hostels.split(",") if h.strip()]

    def payee_aliases_list(self) -> list[str]:
        return [a.strip() for a in self.payee_name_aliases.split(",") if a.strip()]

    def db_url(self) -> str:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return f"sqlite:///{path}"

    def is_paid_llm_enabled(self) -> bool:
        return self.nlu_mode == "llm"

    def placeholders_left(self) -> list[str]:
        """Return names of settings still at an obviously-unset placeholder.
        Used to fail loudly before running a real (non-simulator) channel."""
        issues = []
        if self.upi_vpa.strip().lower() in PLACEHOLDER_MARKERS:
            issues.append("UPI_VPA")
        if self.payee_name.strip().lower() in PLACEHOLDER_MARKERS:
            issues.append("PAYEE_NAME")
        if self.sms_webhook_secret in {"", "dev-secret-change-me"}:
            issues.append("SMS_WEBHOOK_SECRET")
        if self.admin_password in {"", "dev-admin-change-me"}:
            issues.append("ADMIN_PASSWORD")
        if self.channel == "whatsapp":
            for name, val in [
                ("WHATSAPP_TOKEN", self.whatsapp_token),
                ("WHATSAPP_PHONE_NUMBER_ID", self.whatsapp_phone_number_id),
                ("WHATSAPP_VERIFY_TOKEN", self.whatsapp_verify_token),
                ("WHATSAPP_APP_SECRET", self.whatsapp_app_secret),
            ]:
                if not val:
                    issues.append(name)
        return issues


def load_settings() -> Settings:
    return Settings()
