from __future__ import annotations

LANGS = {
    "en": "🇺🇸 English",
    "vi": "🇻🇳 Tiếng Việt",
    "zh": "🇨🇳 中文",
    "id": "🇮🇩 Indonesia",
    "es": "🇪🇸 Español",
    "ru": "🇷🇺 Русский",
    "ar": "العربية",
}

T: dict[str, dict[str, str]] = {
    "vi": {
        "welcome": "🤗 Chào mừng đến với cửa hàng của chúng tôi!",
        "balance_line": "💳 Số dư của bạn: {balance} USDT",
        "shop": "🛍 Cửa hàng",
        "deposit": "💼 Nạp tiền",
        "profile": "👤 Hồ sơ của tôi",
        "support": "✈️ Hỗ trợ",
        "shopee": "🤖 Shopee",
        "earn": "⭐ Kiếm tiền",
        "channel": "Channel",
        "back": "Quay lại",
        "cancel": "Hủy",
        "products_available": "Sản phẩm hiện có:",
        "filter_all": "Lọc: Tất cả",
        "refresh": "🔄 Làm mới",
        "next": "Tiếp",
        "prev": "Trước",
        "page": "{cur}/{total}",
        "out_of_stock": "Hết kho",
        "stock_label": "Kho",
        "set_qty": "SL: {qty}",
        "del": "Del",
        "topup_wallet": "🧩 Nạp Ví",
        "share_link": "🔗 Chia sẻ Link",
        "view_note": "📝 Xem ghi chú",
        "product": "Sản phẩm",
        "orig_price": "🏷 Giá gốc",
        "stock_now": "🦆 Kho hiện có",
        "warranty": "🖋 Bảo hành",
        "promo": "🎁 Khuyến mãi: Mua {min}+ ↪ -{percent}% Giảm",
        "qty": "🔢 Số lượng",
        "total": "🍥 Tổng cộng",
        "wallet": "💳 Ví",
        "insufficient": "❌ Số dư không đủ. Vui lòng nạp thêm.",
        "no_stock": "❌ Sản phẩm hết kho.",
        "buy_success": "✅ Mua thành công {qty}x {name}\n💰 Tổng: {total} USDT\n\n{payload}",
        "max_qty": "❌ Tối đa {n} sản phẩm mỗi lần mua. Hãy chia thành nhiều đơn.",
        "max_per_order": "📦 Tối đa mỗi đơn: {n}",
        "supplier_down": "⚠️ Nhà cung cấp tạm thời không xử lý được đơn. Bạn chưa bị trừ tiền — vui lòng thử lại sau ít phút.",
        "supplier_pending": "⏳ Đơn #{id} đang được xử lý ({total} USDT). Hàng sẽ được gửi tự động ngay khi về — không cần mua lại.",
        "supplier_partial_refund": "↩️ Nhà cung cấp giao thiếu, đã hoàn {amount} USDT vào ví của bạn.",
        "supplier_order_refunded": "↩️ Đơn #{id} không thể hoàn tất. Đã hoàn {amount} USDT vào ví của bạn.",
        "deposit_menu": "Nạp Ví",
        "binance_pay": "🟡 Binance Pay",
        "binance_spot_bep20": "🟠 USDT BEP-20 → Binance",
        "binance_spot_trc20": "🟠 USDT TRC-20 → Binance",
        "usdt_bep20": "🟢 USDT (BEP-20)",
        "ton": "🔵 TON",
        "tron": "🔴 Tron",
        "other": "💡 Khác",
        "binance_instructions": (
            "🟡 *Binance Pay*\n\n"
            "*Pay ID:* `{pay_id}`\n"
            "*Tên:* {pay_name}\n\n"
            "1️⃣ Mở Binance app → Pay → Send → nhập Pay ID `{pay_id}`\n"
            "2️⃣ Chọn *USDT*, gửi *chính xác* số tiền bạn nhập bên dưới\n"
            "3️⃣ Bot sẽ tự cộng balance trong ~30 giây sau khi nhận\n\n"
            "_Nhập số tiền bạn sẽ gửi (VD: 5.25):_"
        ),
        "bep20_instructions": (
            "🟢 *USDT (BEP-20)*\n\n"
            "Địa chỉ ví: `{address}`\n\n"
            "Gửi USDT trên mạng BSC (BEP-20). Số dư sẽ được cộng tự động trong vòng 1-3 phút sau khi giao dịch xác nhận."
        ),
        "ton_instructions": (
            "🔵 *TON*\n\n"
            "Địa chỉ ví: `{address}`\n\n"
            "Gửi TON. Số dư USDT sẽ được cộng tự động dựa theo tỷ giá hiện tại."
        ),
        "tron_instructions": (
            "🔴 *USDT (TRC-20)*\n\n"
            "Địa chỉ ví: `{address}`\n\n"
            "Gửi USDT trên mạng Tron (TRC-20). Số dư sẽ được cộng tự động."
        ),
        "binance_spot_bep20_instructions": (
            "🟠 *Nạp USDT BEP-20 vào Binance*\n\n"
            "Địa chỉ ví Binance (BSC): `{address}`\n\n"
            "Gửi USDT trên mạng BSC (BEP-20) đến địa chỉ Binance ở trên. "
            "Bot sẽ tự động phát hiện qua API Binance trong 1-2 phút sau khi xác nhận."
        ),
        "binance_spot_trc20_instructions": (
            "🟠 *Nạp USDT TRC-20 vào Binance*\n\n"
            "Địa chỉ ví Binance (Tron): `{address}`\n\n"
            "Gửi USDT trên mạng Tron (TRC-20) đến địa chỉ Binance ở trên. "
            "Bot sẽ tự động phát hiện qua API Binance trong 1-2 phút sau khi xác nhận."
        ),
        "other_instructions": "💡 Vui lòng liên hệ admin để được hỗ trợ phương thức khác.",
        "deposit_received": "✅ Đã nhận nạp {amount} USDT. Số dư mới: {balance} USDT",
        "deposit_invalid": "❌ Order ID không hợp lệ hoặc chưa thanh toán. Thử lại.",
        "profile_card": (
            "🧑 *Hồ sơ Người dùng*\n\n"
            "🆔 ID: `{id}`\n"
            "💳 Số dư: `{balance}` USDT\n"
            "🌐 Ngôn ngữ: `{lang_code}`\n"
            "📅 Tham gia: `{joined}`"
        ),
        "notifications": "🔔 Thông báo",
        "my_orders": "💼 Đơn hàng",
        "my_deposits": "💸 Lịch sử nạp",
        "dev_api": "🗄 API Nhà phát triển",
        "language": "🌐 Ngôn ngữ (EN/VI/ZH/ID)",
        "select_lang": "Vui lòng chọn ngôn ngữ:",
        "lang_set": "✅ Đã đặt ngôn ngữ.",
        "orders_title": "💼 Đơn hàng của tôi",
        "valid": "🛡 Còn hạn",
        "expired": "⭐ Hết hạn",
        "no_orders": "Bạn chưa có đơn hàng nào.",
        "earn_card": (
            "⭐ *Giới thiệu & Kiếm tiền*\n\n"
            "🧑‍🤝‍🧑 Giới thiệu (24h): `{d1}`\n"
            "🧑‍🤝‍🧑 Giới thiệu (7 ngày): `{d7}`\n"
            "🧑‍🤝‍🧑 Giới thiệu (Tổng): `{total}`\n\n"
            "💳 Tổng kiếm được: `{earned}` USDT\n"
            "💳 Khả dụng: `{avail}` USDT\n"
            "✅ Đã chuyển: `{transferred}` USDT\n"
            "🛡 Đã rút: `{withdrawn}` USDT\n\n"
            "💡 Kiếm *{rate}%* mỗi lần nạp tiền từ người được giới thiệu.\n"
            "Tối đa *${max}* mỗi lần nạp.\n\n"
            "Liên kết giới thiệu:\n{link}"
        ),
        "copy_link": "📋 Sao chép liên kết",
        "support_title": "✈️ *Hỗ trợ*",
        "support_msg": "Nếu bạn không thể gửi tin nhắn hoặc gặp sự cố, hãy sử dụng *Hỗ trợ Trực tiếp* để kết nối trực tiếp với quản trị viên.",
        "live_support": "✈️ Hỗ trợ Trực tiếp",
        "contact_admin": "👤 Liên hệ Quản trị viên",
        "support_active": "✈️ *Hỗ trợ Trực tiếp*\n\nPhiên hỗ trợ đang hoạt động.\n\nVui lòng nhắn tin cho chúng tôi qua tab *Hỗ trợ Trực tiếp* được tạo ở trên trong cuộc trò chuyện này.",
        "end_support": "Hủy Hỗ trợ",
        "support_ended": "✅ Đã kết thúc phiên hỗ trợ.",
        "api_card": (
            "🗄 *Bảng điều khiển API*\n\n"
            "Quản lý quyền truy cập API và xem thống kê.\n\n"
            "🟢 *Trạng thái API:* {status}\n\n"
            "*Mã API (API Key) của bạn:*\n`{key}`\n\n"
            "⚠️ _Không chia sẻ mã này. Thu hồi ngay lập tức nếu bị lộ._\n\n"
            "🌐 Webhook: `{webhook}`\n"
            "📈 Đơn hàng API: `{orders}`\n"
            "💲 Chi tiêu qua API: `{spend}` USDT"
        ),
        "set_webhook": "🌐 Cài đặt Webhook",
        "revoke_api": "🔒 Thu hồi mã API",
        "view_api_docs": "📄 Xem Tài liệu API",
        "set_webhook_prompt": "🌐 *Cài đặt URL Webhook*\n\nNhập URL HTTPS công khai của máy chủ sẽ nhận thông báo số dư.\n\n> Máy chủ của bạn phải hoạt động trên internet - không phải localhost. Chúng tôi sẽ POST dữ liệu JSON mỗi khi số dư của bạn thay đổi.",
        "webhook_set": "✅ Đã đặt Webhook.",
        "api_revoked": "✅ Đã thu hồi và tạo mã API mới.",
        "send_order_id": "Vui lòng gửi *Order ID* bên dưới:",
        "share_text": "🛍 Tham khảo sản phẩm trên @{bot}: {name}",
        "ref_bonus": "💰 Bạn nhận hoa hồng giới thiệu: +{amount} USDT",
        "support_topic_msg": "✈️ Hỗ trợ Trực tiếp\nUser: {full} (`{id}`) @{username}\nNgôn ngữ: {lang_code}",
        "admin_only": "❌ Bạn không có quyền.",
        "cryptomus": "💠 Cryptomus (crypto)",
        "cryptomus_prompt": (
            "💠 *Cryptomus*\n\n"
            "Thanh toán bằng bất kỳ crypto nào (USDT, BTC, ETH, …) — tự động cộng tiền.\n\n"
            "_Nhập số tiền theo USDT (VD: 5):_"
        ),
        "cryptomus_creating": "⏳ Đang tạo hóa đơn…",
        "cryptomus_created": (
            "💠 *Hóa đơn Cryptomus*\n\n"
            "Số tiền: `{amount}` USDT\n\n"
            "Bấm nút bên dưới để thanh toán. Số dư sẽ được cộng tự động sau khi giao dịch xác nhận (thường 1–3 phút)."
        ),
        "cryptomus_pay_btn": "💳 Thanh toán {amount} USDT",
        "cryptomus_error": "❌ Không tạo được hóa đơn. Thử lại sau hoặc dùng phương thức khác.",
        "cryptomus_min": "❌ Số tiền tối thiểu là 1 USDT.",
        "enter_amount_hint": "_Nhập số tiền bạn sẽ gửi (VD: 5.25):_",
        "invalid_amount": "❌ Số tiền không hợp lệ.",
        "pending_registered": (
            "⏳ Phiên nạp đã đăng ký.\n\n"
            "Vui lòng gửi *chính xác* số tiền:\n`{amount}` USDT\n\n"
            "⚠️ _Đúng cả 4 chữ số thập phân_ — sai 1 số bot sẽ không tự ghi nhận. Bot polling mỗi {interval} giây."
        ),
    }
}

# fallback to vi if other lang missing key
T["en"] = {
    "welcome": "🤗 Welcome to our store!",
    "balance_line": "💳 Your balance: {balance} USDT",
    "shop": "🛍 Shop",
    "deposit": "💼 Deposit",
    "profile": "👤 My Profile",
    "support": "✈️ Support",
    "shopee": "🤖 Shopee",
    "earn": "⭐ Earn",
    "channel": "Channel",
    "back": "Back",
    "cancel": "Cancel",
    "products_available": "Available products:",
    "filter_all": "Filter: All",
    "refresh": "🔄 Refresh",
    "next": "Next",
    "prev": "Prev",
    "page": "{cur}/{total}",
    "out_of_stock": "Out of stock",
    "stock_label": "Stock",
    "set_qty": "Qty: {qty}",
    "del": "Del",
    "topup_wallet": "🧩 Top up wallet",
    "share_link": "🔗 Share link",
    "view_note": "📝 View note",
    "product": "Product",
    "orig_price": "🏷 Price",
    "stock_now": "🦆 Stock",
    "warranty": "🖋 Warranty",
    "promo": "🎁 Promo: Buy {min}+ ↪ -{percent}% Off",
    "qty": "🔢 Quantity",
    "total": "🍥 Total",
    "wallet": "💳 Wallet",
    "insufficient": "❌ Insufficient balance. Please top up.",
    "no_stock": "❌ Out of stock.",
    "buy_success": "✅ Bought {qty}x {name}\n💰 Total: {total} USDT\n\n{payload}",
    "max_qty": "❌ Max {n} per purchase. Please split into several orders.",
    "max_per_order": "📦 Max per order: {n}",
    "supplier_down": "⚠️ The supplier can't process orders right now. You were not charged — please try again in a few minutes.",
    "supplier_pending": "⏳ Order #{id} is being processed ({total} USDT). Your items will be sent automatically as soon as they arrive — no need to buy again.",
    "supplier_partial_refund": "↩️ The supplier delivered fewer items; {amount} USDT was refunded to your wallet.",
    "supplier_order_refunded": "↩️ Order #{id} could not be completed. {amount} USDT was refunded to your wallet.",
    "deposit_menu": "Top up Wallet",
    "binance_pay": "🟡 Binance Pay",
    "binance_spot_bep20": "🟠 USDT BEP-20 → Binance",
    "binance_spot_trc20": "🟠 USDT TRC-20 → Binance",
    "usdt_bep20": "🟢 USDT (BEP-20)",
    "ton": "🔵 TON",
    "tron": "🔴 Tron",
    "other": "💡 Other",
    "binance_instructions": (
        "🟡 *Binance Pay*\n\n*Pay ID:* `{pay_id}`\n*Name:* {pay_name}\n\n"
        "1️⃣ Binance app → Pay → Send → enter Pay ID `{pay_id}`\n"
        "2️⃣ Pick *USDT*, send *exactly* the amount you'll enter below\n"
        "3️⃣ Bot auto-credits within ~30s\n\n"
        "_Enter the amount you'll send (e.g. 5.25):_"
    ),
    "bep20_instructions": "🟢 *USDT (BEP-20)*\n\nAddress: `{address}`\n\nSend USDT on BSC. Auto-credit in 1-3 min.",
    "ton_instructions": "🔵 *TON*\n\nAddress: `{address}`\n\nSend TON. Auto-credit in USDT.",
    "tron_instructions": "🔴 *USDT (TRC-20)*\n\nAddress: `{address}`\n\nSend USDT on Tron.",
    "binance_spot_bep20_instructions": (
        "🟠 *Deposit USDT BEP-20 to Binance*\n\n"
        "Binance address (BSC): `{address}`\n\n"
        "Send USDT on BEP-20 to the address above. "
        "Bot auto-detects via Binance API within 1-2 min after confirmation."
    ),
    "binance_spot_trc20_instructions": (
        "🟠 *Deposit USDT TRC-20 to Binance*\n\n"
        "Binance address (Tron): `{address}`\n\n"
        "Send USDT on TRC-20 to the address above. "
        "Bot auto-detects via Binance API within 1-2 min after confirmation."
    ),
    "other_instructions": "💡 Contact admin for other methods.",
    "deposit_received": "✅ Deposit received: {amount} USDT. New balance: {balance} USDT",
    "deposit_invalid": "❌ Invalid Order ID or not paid. Try again.",
    "profile_card": "🧑 *User Profile*\n\n🆔 ID: `{id}`\n💳 Balance: `{balance}` USDT\n🌐 Language: `{lang_code}`\n📅 Joined: `{joined}`",
    "notifications": "🔔 Notifications",
    "my_orders": "💼 My Orders",
    "my_deposits": "💸 Deposit history",
    "dev_api": "🗄 Developer API",
    "language": "🌐 Language",
    "select_lang": "Please select your language:",
    "lang_set": "✅ Language set.",
    "orders_title": "💼 My Orders",
    "valid": "🛡 Valid",
    "expired": "⭐ Expired",
    "no_orders": "You have no orders yet.",
    "earn_card": (
        "⭐ *Referral & Earn*\n\n"
        "🧑‍🤝‍🧑 Referrals (24h): `{d1}`\n🧑‍🤝‍🧑 Referrals (7d): `{d7}`\n🧑‍🤝‍🧑 Referrals (Total): `{total}`\n\n"
        "💳 Earned: `{earned}` USDT\n💳 Available: `{avail}` USDT\n✅ Transferred: `{transferred}` USDT\n🛡 Withdrawn: `{withdrawn}` USDT\n\n"
        "💡 Earn *{rate}%* on every deposit your referrals make.\nMax *${max}* per deposit.\n\n"
        "Referral link:\n{link}"
    ),
    "copy_link": "📋 Copy link",
    "support_title": "✈️ *Support*",
    "support_msg": "If you can't message or have an issue, use *Live Support* to talk to an admin directly.",
    "live_support": "✈️ Live Support",
    "contact_admin": "👤 Contact Admin",
    "support_active": "✈️ *Live Support*\n\nSession active. Send messages here; admin will reply.",
    "end_support": "End Support",
    "support_ended": "✅ Support session ended.",
    "api_card": (
        "🗄 *API Dashboard*\n\nManage API access and stats.\n\n"
        "🟢 *Status:* {status}\n\n*Your API Key:*\n`{key}`\n\n⚠️ _Never share. Revoke if leaked._\n\n"
        "🌐 Webhook: `{webhook}`\n📈 API Orders: `{orders}`\n💲 API Spend: `{spend}` USDT"
    ),
    "set_webhook": "🌐 Set Webhook",
    "revoke_api": "🔒 Revoke API key",
    "view_api_docs": "📄 View API docs",
    "set_webhook_prompt": "🌐 *Set Webhook URL*\n\nEnter the public HTTPS URL that will receive balance notifications.",
    "webhook_set": "✅ Webhook saved.",
    "api_revoked": "✅ API key revoked and regenerated.",
    "send_order_id": "Please send the *Order ID* below:",
    "share_text": "🛍 Check out on @{bot}: {name}",
    "ref_bonus": "💰 Referral commission: +{amount} USDT",
    "support_topic_msg": "✈️ Live Support\nUser: {full} (`{id}`) @{username}\nLang: {lang_code}",
    "admin_only": "❌ Not allowed.",
    "cryptomus": "💠 Cryptomus (crypto)",
    "cryptomus_prompt": (
        "💠 *Cryptomus*\n\n"
        "Pay with any crypto (USDT, BTC, ETH, …) — credited automatically.\n\n"
        "_Enter the amount in USDT (e.g. 5):_"
    ),
    "cryptomus_creating": "⏳ Creating invoice…",
    "cryptomus_created": (
        "💠 *Cryptomus invoice*\n\n"
        "Amount: `{amount}` USDT\n\n"
        "Tap the button below to pay. Your balance is credited automatically once the payment is confirmed (usually 1–3 min)."
    ),
    "cryptomus_pay_btn": "💳 Pay {amount} USDT",
    "cryptomus_error": "❌ Couldn't create the invoice. Try again later or use another method.",
    "cryptomus_min": "❌ Minimum amount is 1 USDT.",
    "enter_amount_hint": "_Enter the amount you'll send (e.g. 5.25):_",
    "invalid_amount": "❌ Invalid amount.",
    "pending_registered": (
        "⏳ Deposit session registered.\n\n"
        "Send *exactly*:\n`{amount}` USDT\n\n"
        "⚠️ _All 4 decimals must match_ — otherwise the bot won't auto-credit. It polls every {interval}s."
    ),
}

# Stub other locales to inherit english (fallback chain handled in t())
for code in ("zh", "id", "es", "ru", "ar"):
    T[code] = {}


def t(lang: str | None, key: str, /, **kwargs) -> str:
    lang = lang or "en"
    val = T.get(lang, {}).get(key) or T["en"].get(key) or T["vi"].get(key) or key
    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            return val
    return val
