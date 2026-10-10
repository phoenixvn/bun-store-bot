"""Web admin panel — server-rendered HTML, HTTP Basic auth, mounted on /admin."""
from __future__ import annotations

import json
import secrets
from decimal import Decimal, ROUND_HALF_UP
from html import escape

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, or_, select

from bot.config import settings
from bot.database import session_scope
from bot.models import (
    ApiKey,
    Broadcast,
    Deposit,
    DepositStatus,
    Order,
    Product,
    ReferralEarning,
    Setting,
    StockItem,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBasic()


def require_auth(creds: HTTPBasicCredentials = Depends(security)) -> str:
    if not settings.admin_password:
        raise HTTPException(503, "ADMIN_PASSWORD not set")
    user_ok = secrets.compare_digest(creds.username, settings.admin_user)
    pass_ok = secrets.compare_digest(creds.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            401, "Bad credentials", headers={"WWW-Authenticate": "Basic"}
        )
    return creds.username


SHELL = """<!doctype html>
<html lang=vi>
<head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{title} — Bami</title>
<link rel=stylesheet href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
<style>
:root {{
  --bg:#f5f5f7; --surface:#fff; --text:#1d1d1f; --muted:#86868b;
  --border:#e5e5ea; --border-soft:#f0f0f3;
  --blue:#0071e3; --blue-hover:#0077ed; --blue-soft:rgba(0,113,227,.1);
  --red:#ff3b30; --red-soft:rgba(255,59,48,.1);
  --green:#30d158; --orange:#ff9500;
}}
* {{ -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }}
html, body {{ background:var(--bg); }}
body {{
  color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Inter","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px; letter-spacing:-0.005em; line-height:1.5;
  padding:36px 28px; max-width:1240px; margin:0 auto;
}}
h1 {{ font-size:34px; font-weight:600; letter-spacing:-0.025em; margin:0 0 32px; }}
h2 {{ font-size:24px; font-weight:600; letter-spacing:-0.02em; margin:28px 0 16px; }}
h3,h4,h5 {{ font-size:17px; font-weight:600; letter-spacing:-0.01em; margin:22px 0 14px; }}
p {{ color:var(--muted); }}
a {{ color:var(--blue); text-decoration:none; }}
a:hover {{ color:var(--blue-hover); }}
hr {{ border-color:var(--border); }}

/* Nav */
nav.bami {{
  display:flex; gap:2px; background:var(--surface);
  padding:6px; border-radius:12px; margin-bottom:32px;
  overflow-x:auto; box-shadow:0 1px 2px rgba(0,0,0,.04);
}}
nav.bami a {{
  color:var(--text); padding:8px 14px; border-radius:8px;
  font-weight:500; font-size:13px; white-space:nowrap;
  transition:background 120ms ease;
}}
nav.bami a:hover {{ background:rgba(0,0,0,.04); }}
nav.bami a.active {{ background:var(--text); color:var(--surface); }}

/* Cards */
.card {{
  background:var(--surface)!important; border:none!important;
  border-radius:14px!important; box-shadow:0 1px 2px rgba(0,0,0,.04);
  padding:22px!important;
}}
.alert {{ border:none!important; border-radius:12px!important; padding:14px 18px!important; }}
.alert-success {{ background:rgba(48,209,88,.12)!important; color:#146c43!important; }}

/* Stat tiles (use existing .card.p-3 + .fs-2) */
.fs-2 {{ font-size:34px!important; font-weight:600!important; letter-spacing:-0.025em!important; line-height:1.1; }}
.text-muted {{ color:var(--muted)!important; }}
.text-muted.small {{ font-size:13px!important; font-weight:500; }}

/* Buttons */
.btn {{
  border-radius:8px!important; font-weight:500!important; font-size:13px!important;
  padding:7px 14px!important; border:none!important; letter-spacing:-0.005em;
  transition:background 120ms,opacity 120ms!important;
}}
.btn-sm {{ padding:5px 10px!important; font-size:12px!important; border-radius:7px!important; }}
.btn-success {{ background:var(--blue)!important; color:#fff!important; }}
.btn-success:hover {{ background:var(--blue-hover)!important; color:#fff!important; }}
.btn-warning {{ background:var(--orange)!important; color:#fff!important; }}
.btn-warning:hover {{ background:#fa9100!important; color:#fff!important; }}
.btn-outline-primary {{ background:var(--blue-soft)!important; color:var(--blue)!important; }}
.btn-outline-primary:hover {{ background:rgba(0,113,227,.18)!important; color:var(--blue)!important; }}
.btn-outline-secondary {{ background:rgba(0,0,0,.05)!important; color:var(--text)!important; }}
.btn-outline-secondary:hover {{ background:rgba(0,0,0,.08)!important; color:var(--text)!important; }}
.btn-outline-danger {{ background:var(--red-soft)!important; color:var(--red)!important; }}
.btn-outline-danger:hover {{ background:rgba(255,59,48,.18)!important; color:var(--red)!important; }}
.btn-link {{ color:var(--blue)!important; text-decoration:none!important; padding:7px 0!important; }}
.btn-danger {{ background:var(--red)!important; color:#fff!important; }}
.btn-danger:hover {{ background:#ff2d22!important; color:#fff!important; }}

/* Forms */
.form-control,textarea.form-control {{
  border:1px solid var(--border)!important; border-radius:8px!important;
  padding:9px 12px!important; font-size:14px!important;
  background:var(--surface)!important; box-shadow:none!important;
  transition:border-color 120ms,box-shadow 120ms!important;
}}
.form-control:focus,textarea.form-control:focus {{
  border-color:var(--blue)!important;
  box-shadow:0 0 0 3px rgba(0,113,227,.18)!important; outline:none!important;
}}
label,.form-label {{
  font-size:12px; font-weight:500; color:var(--muted);
  margin-bottom:5px; display:block; letter-spacing:0.005em;
}}
.form-check-input {{ border:1px solid var(--border)!important; }}
.form-check-input:checked {{ background-color:var(--blue)!important; border-color:var(--blue)!important; }}
.form-check-label {{ color:var(--text); font-size:13px; font-weight:400; }}

/* Tables */
.table {{ background:transparent!important; margin:0!important; }}
.table thead th {{
  border-bottom:1px solid var(--border)!important;
  background:transparent!important; font-weight:500!important;
  font-size:11px!important; color:var(--muted)!important;
  text-transform:uppercase; letter-spacing:0.06em;
  padding:12px!important;
}}
.table tbody td {{
  border-top:1px solid var(--border-soft)!important; border-bottom:none!important;
  padding:13px 12px!important; vertical-align:middle; font-size:13px;
}}
.table tbody tr:hover {{ background:rgba(0,0,0,.015); }}
.table-striped > tbody > tr:nth-of-type(odd) > * {{ background:transparent!important; }}
.table-sm tbody td,.table-sm thead th {{ padding:9px 10px!important; }}

/* Code */
code {{
  background:rgba(0,0,0,.05); color:var(--text);
  padding:2px 6px; border-radius:5px;
  font-family:"SF Mono",Menlo,Consolas,monospace; font-size:12px;
}}
.font-monospace {{ font-family:"SF Mono",Menlo,Consolas,monospace!important; font-size:13px; }}

.container-fluid {{ padding:0!important; }}
canvas {{ max-height:280px; }}

/* Wrap inline forms naturally */
form[style*="display:inline"] {{ display:inline-block!important; }}
</style>
</head>
<body>
<nav class="bami">
  <a class="{a_dash}" href="/admin/">Dashboard</a>
  <a class="{a_prod}" href="/admin/products">Products</a>
  <a class="{a_ord}" href="/admin/orders">Orders</a>
  <a class="{a_dep}" href="/admin/deposits">Deposits</a>
  <a class="{a_usr}" href="/admin/users">Users</a>
  <a class="{a_aff}" href="/admin/affiliate">Affiliate</a>
  <a class="{a_bc}" href="/admin/broadcast">Broadcast</a>
  <a class="{a_sup}" href="/admin/supplier">Supplier</a>
  <a class="{a_set}" href="/admin/settings">Settings</a>
</nav>
<div class="container-fluid"><h1>{title}</h1>{body}</div>
</body></html>"""


def page(title: str, body: str, active: str = "") -> HTMLResponse:
    return HTMLResponse(SHELL.format(
        title=escape(title), body=body,
        a_dash="active" if active == "dash" else "",
        a_sup="active" if active == "sup" else "",
        a_prod="active" if active == "prod" else "",
        a_ord="active" if active == "ord" else "",
        a_dep="active" if active == "dep" else "",
        a_usr="active" if active == "usr" else "",
        a_aff="active" if active == "aff" else "",
        a_bc="active" if active == "bc" else "",
        a_set="active" if active == "set" else "",
    ))


@router.get("/", response_class=HTMLResponse)
async def dashboard(_: str = Depends(require_auth)):
    cutoff = datetime.utcnow() - timedelta(days=7)
    async with session_scope() as s:
        users = await s.scalar(select(func.count(User.id))) or 0
        orders = await s.scalar(select(func.count(Order.id))) or 0
        revenue = await s.scalar(select(func.coalesce(func.sum(Order.total), 0))) or 0
        pending = await s.scalar(
            select(func.count(Deposit.id)).where(
                Deposit.status == DepositStatus.PENDING.value
            )
        ) or 0
        method_rows = (await s.execute(
            select(
                Deposit.method,
                func.count(Deposit.id),
                func.coalesce(func.sum(Deposit.amount), 0),
            )
            .where(Deposit.status == DepositStatus.APPROVED.value)
            .group_by(Deposit.method)
        )).all()
        # 7-day daily orders + revenue
        daily_orders = (await s.execute(
            select(
                func.date(Order.created_at).label("d"),
                func.count(Order.id),
                func.coalesce(func.sum(Order.total), 0),
            )
            .where(Order.created_at >= cutoff)
            .group_by("d")
            .order_by("d")
        )).all()
        # 7-day daily deposits (approved)
        daily_deps = (await s.execute(
            select(
                func.date(Deposit.created_at).label("d"),
                func.coalesce(func.sum(Deposit.amount), 0),
            )
            .where(
                Deposit.status == DepositStatus.APPROVED.value,
                Deposit.created_at >= cutoff,
            )
            .group_by("d")
            .order_by("d")
        )).all()
    # build 7-day series
    days = [(datetime.utcnow() - timedelta(days=i)).date() for i in range(6, -1, -1)]
    o_map = {row[0]: (row[1], float(row[2])) for row in daily_orders}
    d_map = {row[0]: float(row[1]) for row in daily_deps}
    labels = [d.strftime("%m-%d") for d in days]
    o_counts = [o_map.get(d, (0, 0))[0] for d in days]
    o_rev = [o_map.get(d, (0, 0))[1] for d in days]
    d_amts = [d_map.get(d, 0.0) for d in days]

    method_html = ""
    if method_rows:
        method_html = "<table class='table table-sm bg-white'><thead><tr><th>Method</th><th>Count</th><th>Total USDT</th></tr></thead><tbody>"
        for m, c, total in method_rows:
            method_html += f"<tr><td><code>{escape(m)}</code></td><td>{c}</td><td>{total}</td></tr>"
        method_html += "</tbody></table>"
    else:
        method_html = "<p class='text-muted'>No approved deposits yet.</p>"

    chart_js = f"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
    new Chart(document.getElementById('dailyChart'), {{
      type: 'line',
      data: {{
        labels: {labels},
        datasets: [
          {{label: 'Revenue (USDT)', data: {o_rev}, borderColor: '#198754', backgroundColor: 'rgba(25,135,84,.1)', tension: .3, fill: true, yAxisID: 'y'}},
          {{label: 'Deposits (USDT)', data: {d_amts}, borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,.1)', tension: .3, fill: true, yAxisID: 'y'}},
          {{label: 'Orders', data: {o_counts}, borderColor: '#dc3545', borderDash: [5,3], yAxisID: 'y2', tension: .3}}
        ]
      }},
      options: {{
        scales: {{
          y: {{position: 'left', title: {{display: true, text: 'USDT'}}}},
          y2: {{position: 'right', title: {{display: true, text: 'orders'}}, grid: {{drawOnChartArea: false}}}}
        }}
      }}
    }});
    </script>"""

    body = f"""
    <div class='row g-3 mb-4'>
      <div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Users</div><div class='fs-2'>{users}</div></div></div>
      <div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Orders</div><div class='fs-2'>{orders}</div></div></div>
      <div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Revenue</div><div class='fs-2'>{revenue}</div><div class='text-muted'>USDT</div></div></div>
      <div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Pending deposits</div><div class='fs-2'>{pending}</div></div></div>
    </div>
    <div class='card p-3 mb-4'>
      <h5>Last 7 days</h5>
      <canvas id='dailyChart' height='80'></canvas>
    </div>
    <h4>Deposits by method (A/B)</h4>{method_html}
    {chart_js}
    """
    return page("Dashboard", body, "dash")


@router.get("/products", response_class=HTMLResponse)
async def products_list(_: str = Depends(require_auth)):
    async with session_scope() as s:
        rows = (await s.execute(select(Product).order_by(Product.id))).scalars().all()
        stock_counts = {}
        for p in rows:
            stock_counts[p.id] = await s.scalar(
                select(func.count(StockItem.id)).where(
                    StockItem.product_id == p.id, StockItem.sold.is_(False)
                )
            ) or 0
    form_html = """<form method=post action='/admin/products' class='card p-3 mb-4 row g-2'>
      <div class='col-md-3'><input class='form-control' name='name' placeholder='Name' required></div>
      <div class='col-md-2'><input class='form-control' name='price' placeholder='Price (USDT)' required type=number step='0.0001'></div>
      <div class='col-md-1'><input class='form-control' name='emoji' placeholder='🟢'></div>
      <div class='col-md-2'><input class='form-control' name='warranty' placeholder='Warranty' value='No warranty'></div>
      <div class='col-md-3'><input class='form-control' name='discount_tiers' placeholder='[{"min":5,"percent":5}]'></div>
      <div class='col-md-1'><button class='btn btn-success w-100'>Add</button></div>
    </form>"""
    table = "<table class='table bg-white'><thead><tr><th>ID</th><th>Name</th><th>Cost</th><th>Sell</th><th>Stock</th><th>Active</th><th>Actions</th></tr></thead><tbody>"
    for p in rows:
        stock = "∞" if p.unlimited else stock_counts[p.id]
        cost = p.cost_price if p.cost_price is not None else "—"
        src = ""
        if p.supplier_product_id is not None:
            stock = p.supplier_stock
            src = (
                f" <span class='badge bg-info text-dark'>FatCat #{p.supplier_product_id}"
                f" · {p.supplier_price_vnd or 0:,}đ{' · auto' if p.supplier_auto_price else ''}</span>"
            )
            if not p.supplier_available:
                src += " <span class='badge bg-secondary'>delisted</span>"
        table += (
            f"<tr><td>{p.id}</td>"
            f"<td>{escape(p.emoji or '')} {escape(p.name)}{src}</td>"
            f"<td>{cost}</td>"
            f"<td><b>{p.price}</b></td>"
            f"<td>{stock}</td>"
            f"<td>{'✅' if p.is_active else '❌'}</td>"
            f"<td>"
            f"<a class='btn btn-sm btn-outline-primary' href='/admin/products/{p.id}/edit'>Edit</a> "
            f"<a class='btn btn-sm btn-outline-primary' href='/admin/products/{p.id}/stock'>+Stock</a> "
            f"<form style='display:inline' method=post action='/admin/products/{p.id}/toggle'>"
            f"<button class='btn btn-sm btn-outline-secondary'>Toggle</button></form> "
            f"<form style='display:inline' method=post action='/admin/products/{p.id}/delete' onsubmit='return confirm(\"Delete?\")'>"
            f"<button class='btn btn-sm btn-outline-danger'>×</button></form>"
            f"</td></tr>"
        )
    table += "</tbody></table>"
    return page("Products", form_html + table, "prod")


@router.get("/products/{pid}/edit", response_class=HTMLResponse)
async def product_edit_form(pid: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if not p:
            raise HTTPException(404)
        cost = p.cost_price if p.cost_price is not None else p.price
        promo_block = ""
        if p.promo_price and p.promo_until:
            promo_block = (
                f"<div class='alert alert-success'>🔥 PROMO active: "
                f"<b>{p.promo_price}</b> USDT (was {p.price}) — until "
                f"<code>{p.promo_until.strftime('%Y-%m-%d %H:%M UTC')}</code> "
                f"<form style='display:inline' method=post action='/admin/products/{pid}/promo/clear'>"
                f"<button class='btn btn-sm btn-outline-danger ms-2'>Clear promo</button></form></div>"
            )
        promo_form = (
            f"<form method=post action='/admin/products/{pid}/promo' class='card p-3 mb-3'>"
            f"<h5 class='mb-3'>🔥 Set flash promo</h5>"
            f"<div class='row'>"
            f"<div class='col-md-4 mb-2'><label>Promo price (USDT)</label>"
            f"<input class='form-control' name=promo_price type=number step='0.01' placeholder='Less than {p.price}' required></div>"
            f"<div class='col-md-4 mb-2'><label>Duration (hours)</label>"
            f"<input class='form-control' name=hours type=number value='24' min=1 max=720 required></div>"
            f"<div class='col-md-4 mb-2 d-flex align-items-end'>"
            f"<button class='btn btn-warning'>Activate promo & post to channel</button></div>"
            f"</div></form>"
        )
        supplier_block = ""
        if p.supplier_product_id is not None:
            supplier_block = (
                f"<div class='alert alert-info mb-2'>Linked to FatCat product #{p.supplier_product_id} — "
                f"cost {p.supplier_price_vnd or 0:,} VND, stock {p.supplier_stock}, max {p.supplier_max_qty}/order. "
                f"Cost is refreshed every sync.</div>"
                f"<div class='form-check mb-2'><input class='form-check-input' type=checkbox name=supplier_auto_price id=sap "
                f"{'checked' if p.supplier_auto_price else ''}><label class='form-check-label' for=sap>"
                f"Auto sell price = cost × (1 + SUPPLIER_MARKUP_PERCENT). Untick to keep the Sell USDT above.</label></div>"
            )
        body = f"""{promo_block}{promo_form}
        <form method=post action='/admin/products/{pid}/edit' class='card p-3'>
        <div class='mb-2'><label>Name</label><input class='form-control' name=name value='{escape(p.name)}' required></div>
        <div class='row'>
          <div class='col-md-3 mb-2'><label>Emoji</label><input class='form-control' name=emoji value='{escape(p.emoji or "")}'></div>
          <div class='col-md-3 mb-2'><label>Cost USDT</label><input class='form-control' name=cost_price value='{cost}' type=number step='0.0001' required></div>
          <div class='col-md-3 mb-2'><label>Sell USDT</label><input class='form-control' name=price value='{p.price}' type=number step='0.0001' required></div>
          <div class='col-md-3 mb-2'><label>Warranty</label><input class='form-control' name=warranty value='{escape(p.warranty)}'></div>
        </div>
        <div class='mb-2'><label>Description (shown to customer when unlimited=true)</label><textarea class='form-control' name=description rows=3>{escape(p.description or "")}</textarea></div>
        <div class='mb-2'><label>Discount tiers JSON</label><input class='form-control font-monospace' name=discount_tiers value='{escape(json.dumps(p.discount_tiers or []))}'></div>
        <div class='form-check mb-2'><input class='form-check-input' type=checkbox name=unlimited id=ulim {"checked" if p.unlimited else ""}><label class='form-check-label' for=ulim>Unlimited stock</label></div>
        <div class='form-check mb-2'><input class='form-check-input' type=checkbox name=is_active id=iact {"checked" if p.is_active else ""}><label class='form-check-label' for=iact>Active</label></div>
        {supplier_block}
        <button class='btn btn-success'>Save changes</button>
        <a href='/admin/products' class='btn btn-link'>Back</a>
        </form>"""
    return page(f"Edit #{pid} — {escape(p.name)}", body, "prod")


@router.post("/products/{pid}/edit")
async def product_edit_save(
    pid: int,
    _: str = Depends(require_auth),
    name: str = Form(...),
    emoji: str = Form(""),
    cost_price: Decimal = Form(...),
    price: Decimal = Form(...),
    warranty: str = Form("No warranty"),
    description: str = Form(""),
    discount_tiers: str = Form("[]"),
    unlimited: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    supplier_auto_price: Optional[str] = Form(None),
):
    tiers: list = []
    try:
        tiers = json.loads(discount_tiers) if discount_tiers.strip() else []
        if not isinstance(tiers, list):
            tiers = []
    except Exception:
        tiers = []
    old_price = None
    notif_emoji = ""
    notif_name = ""
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if not p:
            raise HTTPException(404)
        old_price = Decimal(p.price)
        p.name = name
        p.emoji = emoji
        p.cost_price = cost_price
        p.price = price
        p.warranty = warranty
        p.description = description
        p.discount_tiers = tiers
        if p.supplier_product_id is not None:
            p.supplier_auto_price = supplier_auto_price == "on"
            p.unlimited = False  # supplier products always have real (synced) stock
        else:
            p.unlimited = unlimited == "on"
        p.is_active = is_active == "on"
        notif_emoji = p.emoji or ""
        notif_name = p.name
    # Notify channel only if sell price changed
    if old_price is not None and old_price != price:
        from bot.bot_instance import notify_channel

        delta = ((Decimal(price) - old_price) / old_price * Decimal("100")).quantize(Decimal("0.1"))
        arrow = "📈" if price > old_price else "📉"
        verb = "price up" if price > old_price else "price drop"
        await notify_channel(
            f"{arrow} *{verb.upper()}*\n\n"
            f"{notif_emoji} *{notif_name}*\n"
            f"~{old_price}~ → *{price}* USDT  ({delta:+}%)\n\n"
            f"Buy now: /start"
        )
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{pid}/promo")
async def product_set_promo(
    pid: int,
    _: str = Depends(require_auth),
    promo_price: Decimal = Form(...),
    hours: int = Form(...),
):
    if hours <= 0 or hours > 720:
        raise HTTPException(400, "hours must be 1..720 (30 days max)")
    if promo_price <= 0:
        raise HTTPException(400, "promo_price must be > 0")
    until = datetime.utcnow() + timedelta(hours=hours)
    notif_emoji = notif_name = ""
    notif_price = None
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if not p:
            raise HTTPException(404)
        if promo_price >= Decimal(p.price):
            raise HTTPException(400, "promo_price must be lower than current sell price")
        p.promo_price = promo_price
        p.promo_until = until
        notif_emoji = p.emoji or ""
        notif_name = p.name
        notif_price = Decimal(p.price)
    from bot.bot_instance import notify_channel

    pct = ((promo_price - notif_price) / notif_price * Decimal("100")).quantize(Decimal("0.1"))
    duration_label = (
        f"{hours} hours" if hours < 48 else f"{hours // 24} days"
    )
    await notify_channel(
        f"🔥 *FLASH SALE*\n\n"
        f"{notif_emoji} *{notif_name}*\n"
        f"~{notif_price}~ → *{promo_price}* USDT  ({pct:+}%)\n"
        f"⏱ Only for {duration_label}\n\n"
        f"Buy now: /start"
    )
    return RedirectResponse(f"/admin/products/{pid}/edit", status_code=303)


@router.post("/products/{pid}/promo/clear")
async def product_clear_promo(pid: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if p:
            p.promo_price = None
            p.promo_until = None
    return RedirectResponse(f"/admin/products/{pid}/edit", status_code=303)


@router.post("/products/{pid}/delete")
async def product_delete(pid: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if p:
            await s.delete(p)
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products")
async def products_create(
    _: str = Depends(require_auth),
    name: str = Form(...),
    price: Decimal = Form(...),
    emoji: str = Form(""),
    warranty: str = Form("No warranty"),
    discount_tiers: str = Form(""),
):
    tiers: list = []
    if discount_tiers.strip():
        try:
            tiers = json.loads(discount_tiers)
            if not isinstance(tiers, list):
                tiers = []
        except Exception:
            tiers = []
    async with session_scope() as s:
        new_p = Product(
            name=name, cost_price=price, price=price, emoji=emoji,
            warranty=warranty, discount_tiers=tiers,
        )
        s.add(new_p)
        await s.flush()
        new_id = new_p.id
        new_emoji = new_p.emoji
        new_price = new_p.price
    # Auto-post to channel if configured
    if settings.channel_id:
        from bot.bot_instance import bot

        if bot:
            try:
                deep = f"https://t.me/{settings.bot_username}?start=prod_{new_id}"
                await bot.send_message(
                    chat_id=settings.channel_id,
                    text=(
                        f"🆕 *New product*\n\n"
                        f"{new_emoji} *{name}* — `{new_price}` USDT\n\n"
                        f"Buy now: {deep}"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{pid}/toggle")
async def products_toggle(pid: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if p:
            p.is_active = not p.is_active
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/products/{pid}/stock", response_class=HTMLResponse)
async def stock_form(pid: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        p = await s.get(Product, pid)
        if not p:
            raise HTTPException(404)
        prod_name = p.name
    body = f"""
    <p>Adding stock to <b>#{pid} {escape(prod_name)}</b>. One key per line.</p>
    <form method=post action='/admin/products/{pid}/stock' class='card p-3'>
      <textarea class='form-control font-monospace' name=keys rows=18 placeholder='key1@example.com:pass1&#10;key2@example.com:pass2'></textarea>
      <button class='btn btn-success mt-3'>Add to stock</button>
      <a href='/admin/products' class='btn btn-link'>Back</a>
    </form>"""
    return page(f"+ Stock for #{pid}", body, "prod")


@router.post("/products/{pid}/stock")
async def stock_add(
    pid: int, _: str = Depends(require_auth), keys: str = Form(...)
):
    lines = [k.strip() for k in keys.splitlines() if k.strip()]
    async with session_scope() as s:
        for k in lines:
            s.add(StockItem(product_id=pid, payload=k))
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/orders", response_class=HTMLResponse)
async def orders_list(_: str = Depends(require_auth)):
    async with session_scope() as s:
        rows = (await s.execute(
            select(Order).order_by(Order.id.desc()).limit(200)
        )).scalars().all()
    body = "<table class='table table-sm bg-white'><thead><tr><th>#</th><th>User</th><th>Product</th><th>Qty</th><th>Total</th><th>Discount</th><th>Via API</th><th>Status</th><th>Date</th></tr></thead><tbody>"
    for o in rows:
        body += (
            f"<tr><td>{o.id}</td><td>{o.user_id}</td>"
            f"<td>{escape(o.product_name)}</td><td>{o.quantity}</td>"
            f"<td>{o.total}</td><td>{o.discount_percent}%</td>"
            f"<td>{'✓' if o.via_api else ''}</td><td>{escape(o.status)}</td>"
            f"<td>{o.created_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"
        )
    body += "</tbody></table>"
    return page("Orders (last 200)", body, "ord")


@router.get("/deposits", response_class=HTMLResponse)
async def deposits_list(_: str = Depends(require_auth)):
    async with session_scope() as s:
        rows = (await s.execute(
            select(Deposit).order_by(Deposit.id.desc()).limit(200)
        )).scalars().all()
    body = "<table class='table table-sm bg-white'><thead><tr><th>#</th><th>User</th><th>Method</th><th>Amount</th><th>Status</th><th>External ID</th><th>Date</th><th>Actions</th></tr></thead><tbody>"
    for d in rows:
        actions = ""
        if d.status == DepositStatus.PENDING.value:
            actions = (
                f"<form style='display:inline' method=post action='/admin/deposits/{d.id}/approve'>"
                f"<button class='btn btn-sm btn-success'>Approve</button></form> "
                f"<form style='display:inline' method=post action='/admin/deposits/{d.id}/reject'>"
                f"<button class='btn btn-sm btn-danger'>Reject</button></form>"
            )
        ext = escape((d.external_id or "")[:32])
        body += (
            f"<tr><td>{d.id}</td><td>{d.user_id}</td>"
            f"<td><code>{escape(d.method)}</code></td><td>{d.amount}</td>"
            f"<td>{escape(d.status)}</td><td><code>{ext}</code></td>"
            f"<td>{d.created_at.strftime('%Y-%m-%d %H:%M')}</td><td>{actions}</td></tr>"
        )
    body += "</tbody></table>"
    return page("Deposits (last 200)", body, "dep")


@router.post("/deposits/{dep_id}/approve")
async def deposits_approve(dep_id: int, _: str = Depends(require_auth)):
    from bot.services import credit_balance

    async with session_scope() as s:
        d = await s.get(Deposit, dep_id)
        uid, amount = None, None
        if d and d.status == DepositStatus.PENDING.value:
            d.status = DepositStatus.APPROVED.value
            uid, amount = d.user_id, d.amount
    if uid is not None:
        await credit_balance(uid, Decimal(amount))
    return RedirectResponse("/admin/deposits", status_code=303)


@router.post("/deposits/{dep_id}/reject")
async def deposits_reject(dep_id: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        d = await s.get(Deposit, dep_id)
        if d:
            d.status = DepositStatus.REJECTED.value
    return RedirectResponse("/admin/deposits", status_code=303)


@router.get("/users", response_class=HTMLResponse)
async def users_list(_: str = Depends(require_auth), q: str = Query("")):
    q = q.strip()
    async with session_scope() as s:
        stmt = select(User).order_by(User.created_at.desc()).limit(200)
        if q:
            like = f"%{q}%"
            conds = [
                User.username.ilike(like),
                User.full_name.ilike(like),
            ]
            if q.lstrip("-").isdigit():
                conds.append(User.id == int(q))
            stmt = (
                select(User).where(or_(*conds)).order_by(User.created_at.desc()).limit(200)
            )
        rows = (await s.execute(stmt)).scalars().all()
    search_html = (
        f"<form method=get action='/admin/users' class='mb-3'>"
        f"<input class='form-control' name=q value='{escape(q)}' placeholder='Search by id, username, name...'>"
        f"</form>"
    )
    table = "<table class='table'><thead><tr><th>ID</th><th>Username</th><th>Name</th><th>Balance</th><th>Ref by</th><th>Lang</th><th>Joined</th><th>Credit</th></tr></thead><tbody>"
    for u in rows:
        ref_label = f"<code>{u.referrer_id}</code>" if u.referrer_id else "—"
        credit_form = (
            f"<form method=post action='/admin/users/{u.id}/credit' class='d-flex gap-1'>"
            f"<input class='form-control form-control-sm' style='width:80px' name=amount type=number step='0.01' placeholder='+/-USDT' required>"
            f"<input type=hidden name=note value='admin manual credit'>"
            f"<button class='btn btn-sm btn-outline-primary' onclick='return confirm(\"Credit user balance?\")'>Apply</button>"
            f"</form>"
        )
        table += (
            f"<tr><td><code>{u.id}</code></td>"
            f"<td>@{escape(u.username or '')}</td>"
            f"<td>{escape(u.full_name or '')}</td>"
            f"<td><b>{u.balance}</b></td>"
            f"<td>{ref_label}</td>"
            f"<td>{escape(u.language)}</td>"
            f"<td>{u.created_at.strftime('%Y-%m-%d')}</td>"
            f"<td>{credit_form}</td></tr>"
        )
    table += "</tbody></table>"
    return page(
        f"Users ({len(rows)}{' filtered' if q else ' last 200'})",
        search_html + table,
        "usr",
    )


@router.post("/users/{uid}/credit")
async def user_credit(
    uid: int,
    _: str = Depends(require_auth),
    amount: Decimal = Form(...),
    note: str = Form("admin manual credit"),
):
    """Manually credit (or debit) a user's balance. Negative amount allowed."""
    from bot.services import credit_balance

    new_bal = await credit_balance(uid, amount)
    # Log as a Deposit row for audit trail
    async with session_scope() as s:
        s.add(Deposit(
            user_id=uid,
            method="admin_manual",
            amount=amount,
            status=DepositStatus.APPROVED.value,
            external_id=f"manual_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uid}",
            raw={"note": note},
        ))
    return RedirectResponse(f"/admin/users?q={uid}", status_code=303)


@router.get("/affiliate", response_class=HTMLResponse)
async def affiliate_dashboard(_: str = Depends(require_auth)):
    async with session_scope() as s:
        total_referred = await s.scalar(
            select(func.count(User.id)).where(User.referrer_id.is_not(None))
        ) or 0
        total_earnings = await s.scalar(
            select(func.coalesce(func.sum(ReferralEarning.amount), 0))
        ) or 0
        total_referrers = await s.scalar(
            select(func.count(func.distinct(ReferralEarning.referrer_id)))
        ) or 0
        # Leaderboard: top 20 by total earned
        leaderboard = (await s.execute(
            select(
                ReferralEarning.referrer_id,
                func.count(ReferralEarning.id),
                func.coalesce(func.sum(ReferralEarning.amount), 0),
                func.max(ReferralEarning.created_at),
            )
            .group_by(ReferralEarning.referrer_id)
            .order_by(func.sum(ReferralEarning.amount).desc())
            .limit(20)
        )).all()
        # Recent earnings
        recent = (await s.execute(
            select(ReferralEarning).order_by(ReferralEarning.id.desc()).limit(50)
        )).scalars().all()
        # Referrers with signups but zero earnings yet
        zero_earners = (await s.execute(
            select(User.referrer_id, func.count(User.id))
            .where(User.referrer_id.is_not(None))
            .group_by(User.referrer_id)
            .order_by(func.count(User.id).desc())
            .limit(10)
        )).all()
        # Map referrer ids to display names
        all_ids = {r[0] for r in leaderboard} | {r.referrer_id for r in recent} | {r.referee_id for r in recent} | {r[0] for r in zero_earners}
        users_by_id = {}
        if all_ids:
            urows = (await s.execute(select(User).where(User.id.in_(all_ids)))).scalars().all()
            users_by_id = {u.id: u for u in urows}

    def label(uid):
        u = users_by_id.get(uid)
        if not u:
            return f"`{uid}`"
        nm = escape(u.full_name or "—")
        un = "@" + escape(u.username) if u.username else "—"
        return f"{nm} ({un})"

    rate_pct = settings.referral_rate * 100
    settings_html = (
        f"<div class='card p-3 mb-3'>"
        f"<div class='row'>"
        f"<div class='col-md-3'><div class='text-muted small'>Rate per deposit</div><div class='fs-2'>{rate_pct:.0f}%</div></div>"
        f"<div class='col-md-3'><div class='text-muted small'>Cap / deposit</div><div class='fs-2'>${settings.referral_max_per_deposit}</div></div>"
        f"<div class='col-md-3'><div class='text-muted small'>Min withdraw</div><div class='fs-2'>${settings.referral_min_withdraw}</div></div>"
        f"</div><div class='text-muted small mt-2'>Adjust via env vars: <code>REFERRAL_RATE</code>, <code>REFERRAL_MAX_PER_DEPOSIT</code>, <code>REFERRAL_MIN_WITHDRAW</code></div></div>"
    )

    stats_html = (
        f"<div class='row g-3 mb-4'>"
        f"<div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Active referrers</div><div class='fs-2'>{total_referrers}</div></div></div>"
        f"<div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Referred users</div><div class='fs-2'>{total_referred}</div></div></div>"
        f"<div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Total paid out</div><div class='fs-2'>{total_earnings}</div><div class='text-muted'>USDT</div></div></div>"
        f"<div class='col-md-3'><div class='card p-3'><div class='text-muted small'>Avg per referrer</div><div class='fs-2'>{(Decimal(total_earnings)/Decimal(total_referrers) if total_referrers else Decimal(0)):.2f}</div></div></div>"
        f"</div>"
    )

    lb_html = "<h2>Top referrers</h2>"
    if leaderboard:
        lb_html += "<table class='table'><thead><tr><th>Referrer</th><th>Referrals paid</th><th>Total earned</th><th>Last earning</th></tr></thead><tbody>"
        for r_id, count, total, last in leaderboard:
            lb_html += (
                f"<tr><td>{label(r_id)}</td>"
                f"<td>{count}</td><td><b>{total}</b> USDT</td>"
                f"<td>{last.strftime('%Y-%m-%d %H:%M') if last else '—'}</td></tr>"
            )
        lb_html += "</tbody></table>"
    else:
        lb_html += "<p>No earnings yet.</p>"

    zero_html = "<h2>Top referrers by signups (no earnings yet)</h2>"
    zero_filtered = [(rid, cnt) for rid, cnt in zero_earners if rid not in {r[0] for r in leaderboard}]
    if zero_filtered:
        zero_html += "<table class='table table-sm'><thead><tr><th>Referrer</th><th>Signups</th></tr></thead><tbody>"
        for rid, cnt in zero_filtered:
            zero_html += f"<tr><td>{label(rid)}</td><td>{cnt}</td></tr>"
        zero_html += "</tbody></table>"
    else:
        zero_html += "<p>—</p>"

    rec_html = "<h2>Recent earnings (last 50)</h2>"
    if recent:
        rec_html += "<table class='table table-sm'><thead><tr><th>#</th><th>Referrer</th><th>Referee</th><th>Amount</th><th>Deposit ID</th><th>Date</th></tr></thead><tbody>"
        for re_row in recent:
            rec_html += (
                f"<tr><td>{re_row.id}</td>"
                f"<td>{label(re_row.referrer_id)}</td>"
                f"<td>{label(re_row.referee_id)}</td>"
                f"<td>{re_row.amount}</td>"
                f"<td>#{re_row.deposit_id}</td>"
                f"<td>{re_row.created_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"
            )
        rec_html += "</tbody></table>"
    else:
        rec_html += "<p>—</p>"

    return page(
        "Affiliate program",
        settings_html + stats_html + lb_html + zero_html + rec_html,
        "aff",
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(_: str = Depends(require_auth)):
    from bot import runtime_settings as rs

    rows = await rs.get_all()
    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r["group"], []).append(r)
    body = (
        "<form method=post action='/admin/settings'>"
        "<p class='text-muted'>Override env vars at runtime. Saved to database, "
        "applied immediately to the running bot, persisted across restarts. "
        "Empty value clears override and falls back to env.</p>"
    )
    for group, items in grouped.items():
        body += f"<div class='card p-3 mb-3'><h3>{escape(group)}</h3>"
        for r in items:
            badge = " <span class='text-muted small'>(overridden)</span>" if r["overridden"] else " <span class='text-muted small'>(env default)</span>"
            body += (
                f"<div class='mb-3'>"
                f"<label><code>{r['env_key']}</code> — {escape(r['label'])}{badge}</label>"
                f"<input class='form-control' name='{r['env_key']}' value='{escape(str(r['value']))}'>"
                f"</div>"
            )
        body += "</div>"
    body += "<button class='btn btn-success'>Save all</button></form>"
    return page("Settings", body, "set")


@router.post("/settings")
async def settings_save(request: Request, _: str = Depends(require_auth)):
    from bot import runtime_settings as rs

    form = await request.form()
    saved = 0
    for key in list(rs.EDITABLE.keys()):
        if key in form:
            await rs.set_value(key, str(form[key]))
            saved += 1
    return RedirectResponse("/admin/settings", status_code=303)


@router.get("/db-dump")
async def db_dump(_: str = Depends(require_auth)):
    """JSON snapshot of every table. Curl + redirect to file as a poor-man's backup."""
    def serialize(v):
        if isinstance(v, (Decimal,)):
            return str(v)
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    out: dict = {"_dumped_at": datetime.utcnow().isoformat()}
    async with session_scope() as s:
        for table in (User, Product, StockItem, Order, Deposit, ReferralEarning, ApiKey, Setting):
            rows = (await s.execute(select(table))).scalars().all()
            out[table.__tablename__] = [
                {c.name: serialize(getattr(r, c.name)) for c in table.__table__.columns}
                for r in rows
            ]
    return JSONResponse(out)


@router.post("/markup")
async def markup_prices(factor: float, _: str = Depends(require_auth)):
    """Idempotent: price = cost_price * factor. Re-runs are safe.
    Skips auto-priced FatCat products — their price follows SUPPLIER_MARKUP_PERCENT."""
    if factor <= 0 or factor > 10:
        raise HTTPException(400, "invalid factor (0 < factor <= 10)")
    f = Decimal(str(factor))
    samples = []
    async with session_scope() as s:
        rows = (await s.execute(
            select(Product).where(
                or_(Product.supplier_product_id.is_(None), Product.supplier_auto_price.is_(False))
            )
        )).scalars().all()
        for p in rows:
            cost = Decimal(p.cost_price) if p.cost_price is not None else Decimal(p.price)
            if p.cost_price is None:
                p.cost_price = cost
            new = (cost * f).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if len(samples) < 5:
                samples.append({"id": p.id, "name": p.name, "cost": str(cost), "new_price": str(new)})
            p.price = new
    # Single channel summary instead of per-product spam
    from bot.bot_instance import notify_channel

    pct = round((float(factor) - 1) * 100, 1)
    direction = "🔻 PRICE DROP" if factor < 1 else "📈 PRICE UPDATE"
    await notify_channel(
        f"{direction} — STORE-WIDE\n"
        f"Factor: ×{factor} ({pct:+}%)\n"
        f"{len(samples)} products updated\n\n"
        f"Browse store: /start"
    )
    return {"updated": len(rows), "factor": factor, "samples": samples}


@router.post("/import-products")
async def import_products(
    _: str = Depends(require_auth),
    payload: list[dict] = Body(...),
):
    """Bulk import. Sets cost_price=imported value, price=cost_price (no markup).
    Run /admin/markup?factor=X afterwards to apply sell markup.
    Dedupes by name (case-insensitive)."""
    inserted = skipped = 0
    async with session_scope() as s:
        existing = {
            (p.name or "").lower()
            for p in (await s.execute(select(Product))).scalars().all()
        }
        for item in payload:
            name = (item.get("name") or "").strip()
            if not name or name.lower() in existing:
                skipped += 1
                continue
            try:
                price = Decimal(str(item.get("price_usdt") or "0"))
            except Exception:
                skipped += 1
                continue
            if price <= 0:
                skipped += 1
                continue
            s.add(Product(
                name=name,
                emoji=item.get("emoji") or "",
                cost_price=price,
                price=price,
                warranty=item.get("warranty") or "No warranty",
                description=item.get("description") or "",
                unlimited=True,
                is_active=True,
            ))
            existing.add(name.lower())
            inserted += 1
    return {"inserted": inserted, "skipped": skipped, "total": len(payload)}


def _broadcast_form_html(prefill: dict | None = None) -> str:
    from bot.services.broadcast import AUDIENCES

    p = prefill or {}
    audience_options = ""
    for key, label in AUDIENCES.items():
        sel = "selected" if p.get("audience") == key else ""
        audience_options += f"<option value='{key}' {sel}>{escape(label)}</option>"
    text = escape(p.get("text", ""))
    audience_param = escape(p.get("audience_param", ""))
    to_users_chk = "checked" if p.get("to_users", True) else ""
    to_channel_chk = "checked" if p.get("to_channel") else ""
    pm_md = "checked" if p.get("parse_mode", "Markdown") == "Markdown" else ""
    pm_pl = "checked" if p.get("parse_mode") == "plain" else ""
    return f"""<form method=post action='/admin/broadcast' class='card p-3'>
      <h3 class='mb-3'>Compose</h3>
      <div class='mb-3'>
        <label>Audience</label>
        <select class='form-control' name=audience>{audience_options}</select>
        <div class='text-muted small mt-1'>For "by_lang" enter <code>vi/en/zh/id/es/ru/ar</code>; for "ids" paste IDs separated by comma or newline.</div>
      </div>
      <div class='mb-3'>
        <label>Audience param (only for by_lang / ids)</label>
        <input class='form-control' name=audience_param value='{audience_param}'>
      </div>
      <div class='mb-3'>
        <label>Message body</label>
        <textarea class='form-control' name=text rows=10 required>{text}</textarea>
      </div>
      <div class='row mb-3'>
        <div class='col-md-6'>
          <label class='mb-1'>Format</label>
          <div class='form-check'><input class='form-check-input' type=radio name=parse_mode value=Markdown id=md {pm_md}><label for=md class='form-check-label'>Markdown (bold/italic/links)</label></div>
          <div class='form-check'><input class='form-check-input' type=radio name=parse_mode value=plain id=pl {pm_pl}><label for=pl class='form-check-label'>Plain text</label></div>
        </div>
        <div class='col-md-6'>
          <label class='mb-1'>Targets</label>
          <div class='form-check'><input class='form-check-input' type=checkbox name=to_users id=us {to_users_chk}><label for=us class='form-check-label'>DM users (uses Audience above)</label></div>
          <div class='form-check'><input class='form-check-input' type=checkbox name=to_channel id=ch {to_channel_chk}><label for=ch class='form-check-label'>Post to channel</label></div>
        </div>
      </div>
      <button class='btn btn-warning' onclick='return confirm("Send broadcast?")'>Send broadcast</button>
      <a href='/admin/broadcasts' class='btn btn-link'>View history</a>
    </form>"""


@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_compose(_: str = Depends(require_auth), resend: int | None = None):
    prefill = None
    if resend:
        async with session_scope() as s:
            bc = await s.get(Broadcast, resend)
        if bc:
            prefill = {
                "audience": bc.audience,
                "audience_param": bc.audience_param,
                "text": bc.text,
                "parse_mode": bc.parse_mode,
                "to_users": bc.to_users,
                "to_channel": bc.to_channel,
            }
    return page("New broadcast", _broadcast_form_html(prefill), "bc")


@router.post("/broadcast", response_class=HTMLResponse)
async def broadcast_send(
    _: str = Depends(require_auth),
    audience: str = Form("all"),
    audience_param: str = Form(""),
    text: str = Form(...),
    parse_mode: str = Form("Markdown"),
    to_users: Optional[str] = Form(None),
    to_channel: Optional[str] = Form(None),
):
    from bot.services.broadcast import execute_broadcast

    res = await execute_broadcast(
        audience=audience,
        audience_param=audience_param,
        text=text,
        parse_mode=parse_mode,
        to_users=to_users == "on",
        to_channel=to_channel == "on",
    )
    return RedirectResponse(f"/admin/broadcasts/{res['id']}", status_code=303)


@router.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts_history(_: str = Depends(require_auth)):
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Broadcast).order_by(Broadcast.id.desc()).limit(100)
            )
        ).scalars().all()
    body = "<a href='/admin/broadcast' class='btn btn-success mb-3'>+ New broadcast</a>"
    body += "<table class='table'><thead><tr><th>#</th><th>Date</th><th>Audience</th><th>Snippet</th><th>Sent / Failed</th><th>Channel</th><th></th></tr></thead><tbody>"
    for b in rows:
        snippet = (b.text[:60] + "…") if len(b.text) > 60 else b.text
        ch = "✅" if b.channel_ok else ("—" if not b.to_channel else "❌")
        aud_label = f"{b.audience}" + (f":{b.audience_param}" if b.audience_param else "")
        body += (
            f"<tr><td>{b.id}</td>"
            f"<td>{b.created_at.strftime('%Y-%m-%d %H:%M')}</td>"
            f"<td><code>{escape(aud_label)}</code></td>"
            f"<td>{escape(snippet)}</td>"
            f"<td>{b.sent}/{b.failed} <span class='text-muted small'>of {b.recipients}</span></td>"
            f"<td>{ch}</td>"
            f"<td><a class='btn btn-sm btn-outline-primary' href='/admin/broadcasts/{b.id}'>View</a></td>"
            f"</tr>"
        )
    body += "</tbody></table>"
    return page("Broadcast history", body, "bc")


@router.get("/broadcasts/{bc_id}", response_class=HTMLResponse)
async def broadcast_detail(bc_id: int, _: str = Depends(require_auth)):
    async with session_scope() as s:
        b = await s.get(Broadcast, bc_id)
        if not b:
            raise HTTPException(404)
    aud_label = b.audience + (f" ({b.audience_param})" if b.audience_param else "")
    ch_status = (
        "✅ Posted" if b.channel_ok
        else ("not requested" if not b.to_channel else "❌ Failed")
    )
    body = f"""
    <div class='card p-3 mb-3'>
      <div class='row'>
        <div class='col-md-3'><div class='text-muted small'>Sent / total</div><div class='fs-2'>{b.sent}/{b.recipients}</div></div>
        <div class='col-md-3'><div class='text-muted small'>Failed</div><div class='fs-2'>{b.failed}</div></div>
        <div class='col-md-3'><div class='text-muted small'>Channel</div><div>{ch_status}</div></div>
        <div class='col-md-3'><div class='text-muted small'>Sent at</div><div>{b.created_at.strftime('%Y-%m-%d %H:%M UTC')}</div></div>
      </div>
      <hr>
      <div><b>Audience:</b> <code>{escape(aud_label)}</code></div>
      <div><b>Format:</b> <code>{escape(b.parse_mode)}</code> &nbsp; <b>DM users:</b> {'yes' if b.to_users else 'no'} &nbsp; <b>To channel:</b> {'yes' if b.to_channel else 'no'}</div>
    </div>
    <div class='card p-3 mb-3'>
      <h5>Message body</h5>
      <pre style='white-space:pre-wrap;font-family:inherit;background:transparent;margin:0'>{escape(b.text)}</pre>
    </div>
    <a class='btn btn-success' href='/admin/broadcast?resend={b.id}'>Edit & resend</a>
    <a class='btn btn-link' href='/admin/broadcasts'>Back to history</a>
    """
    return page(f"Broadcast #{b.id}", body, "bc")


# ---------------------------------------------------------------- FatCat supplier

@router.get("/supplier", response_class=HTMLResponse)
async def supplier_page(_: str = Depends(require_auth), msg: str = Query("")):
    from bot.suppliers import fatcat

    if not fatcat.enabled():
        return page(
            "Supplier",
            "<div class='alert alert-warning'>Set <code>SUPPLIER_API_KEY</code> to enable FatCat.</div>",
            "sup",
        )
    try:
        bal = f"{await fatcat.balance_vnd():,} VND"
    except Exception as e:
        bal = f"<span class='text-danger'>error: {escape(str(e))}</span>"
    async with session_scope() as s:
        pending = (await s.execute(
            select(Order).where(Order.status == "pending").order_by(Order.id.desc()).limit(100)
        )).scalars().all()
        linked = await s.scalar(
            select(func.count(Product.id)).where(Product.supplier_product_id.is_not(None))
        ) or 0
    flash = f"<div class='alert alert-success'>{escape(msg)}</div>" if msg else ""
    body = f"""{flash}
    <div class='card p-3 mb-3'>
      <p class='mb-1'>FatCat wallet: <b>{bal}</b> — top it up in the FatCat bot; every sale is paid from it.</p>
      <p class='mb-1'>Linked products: <b>{linked}</b> · rate <code>{settings.vnd_per_usdt:g}</code> VND/USDT ·
         markup <code>{settings.supplier_markup_percent:g}%</code> (edit under <a href='/admin/settings'>Settings</a>)</p>
      <form method=post action='/admin/supplier/sync' class='mt-2'><button class='btn btn-primary btn-sm'>Sync catalog now</button></form>
    </div>
    <h4>Pending supplier orders ({len(pending)})</h4>
    <p class='text-muted small'>User already paid; the bot retries automatically every 30s with the same request_id (never double-charges).</p>
    <table class='table table-sm bg-white'><thead><tr><th>#</th><th>User</th><th>Product</th><th>Qty</th><th>Total</th><th>request_id</th><th>Attempts</th><th>Last error</th><th></th></tr></thead><tbody>
    """
    for o in pending:
        body += (
            f"<tr><td>{o.id}</td><td>{o.user_id}</td><td>{escape(o.product_name)}</td><td>{o.quantity}</td>"
            f"<td>{o.total}</td><td><code>{escape(o.request_id or '')}</code></td><td>{o.supplier_attempts}</td>"
            f"<td class='small'>{escape(o.supplier_error or '')}</td>"
            f"<td><form method=post action='/admin/supplier/retry/{o.id}'>"
            f"<button class='btn btn-sm btn-outline-primary'>Retry</button></form></td></tr>"
        )
    body += "</tbody></table>"
    return page("Supplier — FatCat", body, "sup")


@router.post("/supplier/sync")
async def supplier_sync(_: str = Depends(require_auth)):
    from urllib.parse import quote

    from bot.services import supplier

    try:
        r = await supplier.sync_products()
        msg = (
            f"Synced {r.seen} products: +{len(r.created)} new, {len(r.linked)} linked, "
            f"-{len(r.removed)} delisted, {r.repriced} repriced."
        )
    except Exception as e:
        msg = f"Sync failed: {e}"
    return RedirectResponse(f"/admin/supplier?msg={quote(msg)}", status_code=303)


@router.post("/supplier/retry/{order_id}")
async def supplier_retry(order_id: int, _: str = Depends(require_auth)):
    from urllib.parse import quote

    from bot.services import supplier

    out = await supplier.fulfill(order_id)
    if out.status != "pending":
        await supplier._deliver_late(order_id, out)
    msg = f"Order #{order_id}: {out.status}" + (f" ({out.error})" if out.error else "")
    return RedirectResponse(f"/admin/supplier?msg={quote(msg)}", status_code=303)
