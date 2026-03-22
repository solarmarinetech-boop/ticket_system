"""
Admin handlers: stats, user management via bot.
"""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models.user import User, UserRole
from app.db.models.ticket import Ticket, TicketStatus

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    waiting_user_id_for_role = State()
    waiting_new_role = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message, is_admin: bool = False):
    if not is_admin:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "🔑 <b>Панель администратора</b>\n\n"
        "/stats — статистика заявок\n"
        "/setrole — назначить роль пользователю\n"
        "/allusers — список всех пользователей\n\n"
        "Также доступна <b>веб-консоль</b> для полного управления.",
        parse_mode="HTML"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: AsyncSession, is_admin: bool = False):
    if not is_admin:
        await message.answer("⛔ Доступ запрещён.")
        return

    result = await db.execute(
        select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    )
    stats = dict(result.all())
    total = sum(stats.values())

    text = (
        f"📊 <b>Статистика заявок</b>\n\n"
        f"Всего: <b>{total}</b>\n"
        f"🆕 Новые: {stats.get(TicketStatus.new, 0)}\n"
        f"⚙️ В работе: {stats.get(TicketStatus.in_progress, 0)}\n"
        f"❓ Ожидают инфо: {stats.get(TicketStatus.waiting_info, 0)}\n"
        f"✅ Закрытые: {stats.get(TicketStatus.closed, 0)}\n"
    )

    exec_result = await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.executor)
    )
    exec_count = exec_result.scalar()
    text += f"\n👷 Исполнителей: {exec_count}"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("allusers"))
async def cmd_all_users(message: Message, db: AsyncSession, is_admin: bool = False):
    if not is_admin:
        await message.answer("⛔ Доступ запрещён.")
        return

    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()

    role_icons = {"admin": "👑", "executor": "🔧", "user": "👤"}
    lines = [f"<b>Все пользователи ({len(users)}):</b>\n"]
    for u in users:
        icon = role_icons.get(u.role, "👤")
        lines.append(f"{icon} {u.full_name} | {u.department or '—'} | ID: <code>{u.telegram_id}</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("setrole"))
async def cmd_set_role(message: Message, state: FSMContext, is_admin: bool = False):
    if not is_admin:
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "Введите <b>Telegram ID</b> пользователя:\n(используйте /allusers чтобы узнать ID)",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_user_id_for_role)


@router.message(AdminStates.waiting_user_id_for_role)
async def process_user_id_for_role(message: Message, state: FSMContext, db: AsyncSession):
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("Неверный формат. Введите числовой Telegram ID.")
        return

    result = await db.execute(select(User).where(User.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return

    await state.update_data(target_user_id=tg_id)
    await message.answer(
        f"Пользователь: <b>{user.full_name}</b>\nТекущая роль: <b>{user.role}</b>\n\n"
        f"Введите новую роль: <code>user</code>, <code>executor</code> или <code>admin</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_new_role)


@router.message(AdminStates.waiting_new_role)
async def process_new_role(message: Message, state: FSMContext, db: AsyncSession):
    role_str = message.text.strip().lower()
    valid_roles = {"user": UserRole.user, "executor": UserRole.executor, "admin": UserRole.admin}

    if role_str not in valid_roles:
        await message.answer("Неверная роль. Введите: user, executor или admin")
        return

    data = await state.get_data()
    tg_id = data.get("target_user_id")
    await state.clear()

    result = await db.execute(select(User).where(User.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        await message.answer("Пользователь не найден.")
        return

    user.role = valid_roles[role_str]
    await db.commit()
    await message.answer(
        f"✅ Роль <b>{user.full_name}</b> изменена на <b>{role_str}</b>.",
        parse_mode="HTML"
    )
