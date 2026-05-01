from __future__ import annotations

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    bot_token: str = Field(alias="BOT_TOKEN")
    bot_username: str = Field(default="bunaistore_bot", alias="BOT_USERNAME")
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")
    support_group_id: int = Field(default=0, alias="SUPPORT_GROUP_ID")
    channel_url: str = Field(default="", alias="CHANNEL_URL")
    admin_username: str = Field(default="", alias="ADMIN_USERNAME")
    default_lang: str = Field(default="vi", alias="DEFAULT_LANG")

    database_url: str = Field(alias="DATABASE_URL")

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    binance_pay_key: str = Field(default="", alias="BINANCE_PAY_KEY")
    binance_pay_secret: str = Field(default="", alias="BINANCE_PAY_SECRET")
    binance_pay_id: str = Field(default="", alias="BINANCE_PAY_ID")
    binance_pay_name: str = Field(default="", alias="BINANCE_PAY_NAME")

    bscscan_api_key: str = Field(default="", alias="BSCSCAN_API_KEY")
    bep20_deposit_address: str = Field(default="", alias="BEP20_DEPOSIT_ADDRESS")
    usdt_bep20_contract: str = Field(
        default="0x55d398326f99059fF775485246999027B3197955",
        alias="USDT_BEP20_CONTRACT",
    )

    toncenter_api_key: str = Field(default="", alias="TONCENTER_API_KEY")
    ton_deposit_address: str = Field(default="", alias="TON_DEPOSIT_ADDRESS")

    trongrid_api_key: str = Field(default="", alias="TRONGRID_API_KEY")
    tron_deposit_address: str = Field(default="", alias="TRON_DEPOSIT_ADDRESS")
    usdt_trc20_contract: str = Field(
        default="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", alias="USDT_TRC20_CONTRACT"
    )

    referral_rate: float = Field(default=0.01, alias="REFERRAL_RATE")
    referral_max_per_deposit: float = Field(default=1.0, alias="REFERRAL_MAX_PER_DEPOSIT")
    referral_min_withdraw: float = Field(default=1.0, alias="REFERRAL_MIN_WITHDRAW")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")
    webhook_hmac_secret: str = Field(default="change_me", alias="WEBHOOK_HMAC_SECRET")

    deposit_poll_interval: int = Field(default=30, alias="DEPOSIT_POLL_INTERVAL")

    @property
    def admin_ids(self) -> List[int]:
        return [int(x) for x in self.admin_ids_raw.split(",") if x.strip().isdigit()]


settings = Settings()  # type: ignore[call-arg]
