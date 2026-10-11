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

### FatCat supplier (`bot/suppliers/fatcat.py`, `bot/services/supplier.py`)

Products with `supplier_product_id` set are sourced live from the FatCat reseller API (VND prices; converted with `VND_PER_USDT` + `SUPPLIER_MARKUP_PERCENT`, both runtime-editable). `sync_loop` upserts the catalog; `buy_product` branches to `_buy_from_supplier`, which debits the user and commits a `pending` Order with a `request_id` **before** calling `/api/buy`. `SupplierError` (definitive 4xx) → refund; `SupplierUnreachable` (timeout/5xx/429) → stay pending, `reconcile_loop` retries with the **same** `request_id` (FatCat dedupes on it). Never refund on an unknown outcome and never generate a new `request_id` for an existing order. Delivered items are stored as sold `StockItem` rows.

### VietQR top-up (`bot/payments/vietqr.py`)

Wallet stays USDT; VND bank transfers are converted at the `VND_PER_USDT` quoted when the QR was created. A PENDING `Deposit(method="vietqr", external_id=<BM memo>)` is only a lookup for *who* paid — a QR can be paid twice, so credits are keyed on the SePay transaction id (first transfer approves the memo row with `raw.sepay_tx`; later ones go through `record_and_credit(external_id="sepay:<tx>")`). Credit the received amount, not the requested one. Transfers without a `BM…` code are ignored (the bank account may be personal).

### UI conventions

Screens edit the message in place via `bot/ui.py::edit_or_send` (falls back to a new message for photos such as QR codes). Product/order screens use `parse_mode="HTML"` with `html.escape` — supplier names/descriptions break Markdown. Inline buttons may carry Bot API `style` (`success`/`primary`/`danger`); never pass `style=None`. Restock/sale DMs come from `supplier.sync_products` events (compare supplier VND, never USDT price) with a per-product `last_notified_at` cooldown.

### Support bridge via forum topics

`User.support_topic_id` stores the Telegram forum-topic ID inside `SUPPORT_GROUP_ID` (a forum-enabled supergroup where the bot is admin). DMs from the user are `copy_to`'d into that thread; admin replies in the thread are `copy_to`'d back to the user (`bot/handlers/support.py`).

### DB URL coercion

`Settings.async_database_url` rewrites `postgres://` and bare `postgresql://` → `postgresql+asyncpg://`. Railway/Heroku-style URLs work without manual editing. Sync drivers will fail — everything (app + Alembic) uses asyncpg.

### i18n

7 languages live in a single `T` dict in `bot/i18n.py` (`vi`, `en`, `zh`, `id`, `es`, `ru`, `ar`). `t(lang, key, **kwargs)` falls back to `en` then to the key itself. New user-facing strings should be added to all 7 maps; missing keys silently render as the key name.

### Config

All env vars are declared once in `bot/config.py::Settings` (pydantic-settings, reads `.env`). `ADMIN_IDS` is a comma-separated string parsed into the `admin_ids` list property. `is_admin(uid)` in `bot/handlers/admin.py` checks against it.
