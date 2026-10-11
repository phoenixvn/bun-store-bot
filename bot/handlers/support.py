from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from bot.config import settings
from bot.database import session_scope
from bot.i18n import t
from bot.keyboards import back_btn, support_kb
from bot.models import User
from bot.services import get_or_create_user

router = Router()
log = logging.getLogger(__name__)


@router.callback_query(F.data == "support")
async def support_menu(cb: CallbackQuery) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    from bot.ui import edit_or_send

    text = (
        t(user.language, "support_title")
        + "\n\n"
        + t(user.language, "support_msg")
        + "\n\n"
        + t(user.language, "support_order_code_hint")
    )
    await edit_or_send(cb, text, support_kb(user.language), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "support:start")
async def support_start(cb: CallbackQuery, bot: Bot) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    lang = user.language
    if not settings.support_group_id:
        await cb.answer("Support not configured", show_alert=True)
        return
    if user.support_topic_id:
        await cb.message.answer(t(lang, "support_active"), parse_mode="Markdown")
        await cb.answer()
        return

    try:
        topic = await bot.create_forum_topic(
            chat_id=settings.support_group_id,
            name=f"{user.full_name or 'user'} ({user.id})",
        )
        async with session_scope() as s:
            u = await s.get(User, user.id)
            u.support_topic_id = topic.message_thread_id
        await bot.send_message(
            chat_id=settings.support_group_id,
            message_thread_id=topic.message_thread_id,
            text=t(
                lang,
                "support_topic_msg",
                full=user.full_name or "",
                id=user.id,
                username=user.username or "—",
                lang_code=lang,
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        log.warning("create_forum_topic failed: %s", e)
        await cb.answer("Failed to start session", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "end_support"), callback_data="support:end")],
        ]
    )
    await cb.message.answer(t(lang, "support_active"), reply_markup=kb, parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "support:end")
async def support_end(cb: CallbackQuery, bot: Bot) -> None:
    user = await get_or_create_user(cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if user.support_topic_id and settings.support_group_id:
        try:
            await bot.close_forum_topic(
                chat_id=settings.support_group_id, message_thread_id=user.support_topic_id
            )
        except Exception:
            pass
    async with session_scope() as s:
        u = await s.get(User, user.id)
        u.support_topic_id = None
    await cb.message.answer(t(user.language, "support_ended"))
    await cb.answer()


# --- bridge user → admin topic ---
@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_to_admin(msg: Message, bot: Bot) -> None:
    if not settings.support_group_id:
        return
    async with session_scope() as s:
        u = await s.get(User, msg.from_user.id)
        if not u or not u.support_topic_id:
            return
        thread_id = u.support_topic_id
    try:
        await msg.copy_to(
            chat_id=settings.support_group_id, message_thread_id=thread_id
        )
    except Exception as e:
        log.warning("forward to support topic failed: %s", e)


# --- admin reply in topic → user DM ---
@router.message(F.chat.id == settings.support_group_id, F.message_thread_id)
async def admin_to_user(msg: Message, bot: Bot) -> None:
    thread_id = msg.message_thread_id
    async with session_scope() as s:
        res = await s.execute(select(User).where(User.support_topic_id == thread_id))
        u = res.scalar_one_or_none()
    if not u:
        return
    try:
        await msg.copy_to(chat_id=u.id)
    except Exception as e:
        log.warning("forward admin reply failed: %s", e)
