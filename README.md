# Bun-style Telegram Store Bot

Clone feature-complete của Bun AI Store style bot: crypto wallet balance, shop với bulk discount, auto-delivery keys, referral 1%, live support via forum topics, Developer API + webhook, 7 ngôn ngữ.

## Quick start

```bash
cp .env.example .env
# điền BOT_TOKEN, DATABASE_URL, SUPPORT_GROUP_ID và ví nhận tiền
pip install -r requirements.txt
alembic revision --autogenerate -m "init"
alembic upgrade head
python -m bot.main
```

## Deploy Railway

1. Push repo lên GitHub
2. Railway → New Project → Deploy from repo
3. Add Postgres plugin → copy `DATABASE_URL` (sửa prefix thành `postgresql+asyncpg://`)
4. Paste tất cả biến trong `.env` vào Railway Variables
5. Deploy. `railway.toml` đã lo `alembic upgrade head` trước khi start.

## Admin setup

- Thêm bot vào group hỗ trợ (forum-enabled), promote admin, copy chat ID vào `SUPPORT_GROUP_ID`
- Chat `/admin` với bot (ID bạn phải trong `ADMIN_IDS`)
- `/admin add_product` để thêm sản phẩm, paste keys để nạp kho

## Payments

- **Binance Pay**: set `BINANCE_PAY_KEY/SECRET`, user dán Order ID → bot query Binance API verify
- **BEP20 USDT**: poller mỗi 30s gọi BscScan API check incoming tx tới `BEP20_DEPOSIT_ADDRESS`
- **TON**: Toncenter poll transactions
- **Tron**: TronGrid poll TRC20 transfers

Mọi deposit auto cộng balance + trigger 1% referral commission (max $1/deposit).

## Developer API

Sidecar FastAPI trên `API_PORT=8080`:
- `GET /v1/balance` — header `X-API-Key: ...`
- `GET /v1/orders`
- `POST /v1/buy` `{product_id, quantity}`
- Webhook POST JSON + header `X-Signature: <hmac-sha256>` khi balance đổi
