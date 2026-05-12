# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt

# DB migrations (Alembic reads bot/config.py → settings.async_database_url)
alembic revision --autogenerate -m "msg"
alembic upgrade head
alembic downgrade -1

# Run (starts aiogram polling + FastAPI sidecar + 3 deposit pollers in one process)
python -m bot.main
```

Production start (Railway): `alembic upgrade head && python -m bot.main` (see `railway.toml`). There is no test suite, linter, or formatter configured — none of those commands exist.

## Architecture

Single-process asyncio app with three concurrent surfaces sharing one DB:

1. **aiogram Dispatcher** (`bot/main.py`) — Telegram bot, long-polling.
2. **FastAPI sidecar** (`bot/api_app.py`, mounted in `bot/main.py` via `uvicorn.Server` task on `API_PORT`) — Developer API authenticated by `X-API-Key` header against the `api_keys` table.
3. **Background pollers** (`bot/payments/{bep20,ton,tron}.py`) — `asyncio.create_task(poll_loop())` per chain. Binance Pay is verified on-demand from `bot/handlers/deposit.py`, not polled.

### Router registration order matters

In `bot/main.py`, `admin.router` is included **first** and `support.router` **last**. The support router has a catch-all `F.chat.type == "private", ~F.text.startswith("/")` handler that relays user DMs into a forum topic — registering anything router-stealing-message after it (or `/admin` after it) breaks those flows.

### Money pipeline (`bot/payments/common.py::record_and_credit`)

Every deposit-credit path funnels through this single function. It:
1. Inserts a `Deposit` row idempotently — duplicate `(method, external_id)` short-circuits (also enforced by `UniqueConstraint`).
2. Calls `services.credit_balance` (`SELECT … FOR UPDATE` on `users`).
3. Awards 1% referral commission (capped at `REFERRAL_MAX_PER_DEPOSIT`) via `services/referral.py`.
4. Posts a webhook to the user's `ApiKey.webhook_url` with HMAC-SHA256 signature in `X-Signature` (secret = `WEBHOOK_HMAC_SECRET`).
5. DM's the user (and the referrer) using the singleton `Bot` from `bot/bot_instance.py`.

When adding a new payment method: build idempotency on `external_id` (tx hash, order id, etc.) and call `record_and_credit` — do not credit balance directly.

### BEP20/TON/Tron pending-session matching

Polled chains can't tell which user sent which tx, so the user first creates a `Deposit` row with `status=PENDING` and a chosen `amount` (see `bot/handlers/deposit.py`). The poller (e.g. `bep20._pending_session_for_tx`) matches incoming on-chain transfers to the most recent `PENDING` deposit with that exact amount. Unmatched txs are logged and left for manual admin assignment via `/admin`.

### Stock locking

`bot/services/order.py::buy_product` selects un-sold `StockItem` rows with `with_for_update(skip_locked=True)` to make concurrent purchases safe — but only when `dialect.name != "sqlite"`. Preserve that branch when modifying; sqlite is supported via `aiosqlite` for local dev.

### Support bridge via forum topics

`User.support_topic_id` stores the Telegram forum-topic ID inside `SUPPORT_GROUP_ID` (a forum-enabled supergroup where the bot is admin). DMs from the user are `copy_to`'d into that thread; admin replies in the thread are `copy_to`'d back to the user (`bot/handlers/support.py`).

### DB URL coercion

`Settings.async_database_url` rewrites `postgres://` and bare `postgresql://` → `postgresql+asyncpg://`. Railway/Heroku-style URLs work without manual editing. Sync drivers will fail — everything (app + Alembic) uses asyncpg.

### i18n

7 languages live in a single `T` dict in `bot/i18n.py` (`vi`, `en`, `zh`, `id`, `es`, `ru`, `ar`). `t(lang, key, **kwargs)` falls back to `en` then to the key itself. New user-facing strings should be added to all 7 maps; missing keys silently render as the key name.

### Config

All env vars are declared once in `bot/config.py::Settings` (pydantic-settings, reads `.env`). `ADMIN_IDS` is a comma-separated string parsed into the `admin_ids` list property. `is_admin(uid)` in `bot/handlers/admin.py` checks against it.
