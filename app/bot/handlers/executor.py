"""
Executor handlers: manage assigned tasks.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.user import User, UserRole
from app.db.models.ticket import Ticket, TicketStatus, TicketComment
from app.services.routing_service import advance_ticket
from app.services.notification import (
    notify_user_ticket_closed, notify_user_ticket_status, notify_executor_ticket_transferred
)
from app.bot.keyboards.inline import (
    ticket_in_progress_keyboard, executor_ticket_keyboard, cancel_keyboard
)

logger = logging.getLogger(__name__)
router = Router()


class ExecutorStates(StatesGroup):
    waiting_comment = State()
    waiting_transfer_id = State()
    waiting_info_request = State()


@router.message(Command("mytasks"))
async def cmd_my_tasks(
    message: Message,
    db: AsyncSession,
    current_user: User | None = None,
    is_executor: bool = False,
):
    if not is_executor or not current_user:
        await message.answer("⛔ Эта команда только для ИТ-сотрудников.")
        return

    result = await db.execute(
        select(Ticket)
        .where(
            Ticket.assignee_id == current_user.id,
            Ticket.status.in_([TicketStatus.new, TicketStatus.in_progress, TicketStatus.waiting_info])
        )
        .order_by(Ticket.created_at.desc())
    )
    tickets = result.scalars().all()

    if not tickets:
        await message.answer("У вас нет активных задач. 🎉")
        return

    text = f"📋 Ваши активные задачи ({len(tickets)}):\n\n"
    for t in tickets:
        status_icon = {"new": "🆕", "in_progress": "⚙️", "waiting_info": "❓"}.get(t.status, "📋")
        text += f"{status_icon} #{t.id} — {t.title[:40]}\n"

    await message.answer(text)


@router.callback_query(F.data.startswith("ticket:start:"))
async def ticket_start(
    callback: CallbackQuery,
    db: AsyncSession,
    current_user: User | None = None,
    is_executor: bool = False,
):
    if not is_executor:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    ticket = await _get_ticket(db, ticket_id)
    if not ticket:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    ticket.status = TicketStatus.in_progress
    ticket.assignee_id = current_user.id
    await db.commit()

    await callback.message.edit_reply_markup(reply_markup=ticket_in_progress_keyboard(ticket_id))
    await callback.answer("✅ Задача взята в работу!")

    creator = await _get_user(db, ticket.creator_id)
    if creator:
        await notify_user_ticket_status(
            callback.bot, creator, ticket,
            f"⚙️ <b>Заявка #{ticket.id} взята в работу</b>\n"
            f"Исполнитель: {current_user.full_name}"
        )


@router.callback_query(F.data.startswith("ticket:done:"))
async def ticket_done(
    callback: CallbackQuery,
    db: AsyncSession,
    current_user: User | None = None,
    is_executor: bool = False,
    state: FSMContext = None,
):
    if not is_executor:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    ticket = await _get_ticket(db, ticket_id)
    if not ticket:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    await state.update_data(pending_ticket_id=ticket_id, pending_action="done")
    await callback.message.answer(
        "💬 Добавьте комментарий к выполненной задаче (или напишите '-' если нечего добавить):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(ExecutorStates.waiting_comment)
    await callback.answer()


@router.message(ExecutorStates.waiting_comment)
async def process_done_comment(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User | None = None,
):
    data = await state.get_data()
    ticket_id = data.get("pending_ticket_id")
    action = data.get("pending_action", "done")
    await state.clear()

    ticket = await _get_ticket(db, ticket_id)
    if not ticket:
        await message.answer("Заявка не найдена.")
        return

    comment_text = message.text.strip() if message.text != "-" else None

    if action == "comment":
        if comment_text:
            comment = TicketComment(
                ticket_id=ticket_id,
                author_id=current_user.id,
                text=comment_text,
            )
            db.add(comment)
            await db.commit()
        await message.answer(f"✅ Комментарий добавлен к заявке #{ticket_id}.")
        return

    if comment_text:
        comment = TicketComment(
            ticket_id=ticket_id,
            author_id=current_user.id,
            text=comment_text,
        )
        db.add(comment)

    next_executor, is_finished = await advance_ticket(db, ticket)

    if is_finished:
        creator = await _get_user(db, ticket.creator_id)
        if creator:
            await notify_user_ticket_closed(message.bot, creator, ticket, comment_text)
        await message.answer(f"✅ Заявка #{ticket_id} закрыта! Пользователь уведомлён.")
    else:
        if next_executor:
            await notify_executor_ticket_transferred(message.bot, next_executor, ticket, current_user)
            try:
                await message.bot.send_message(
                    next_executor.telegram_id,
                    f"📋 Задача #{ticket.id}:",
                    reply_markup=executor_ticket_keyboard(ticket.id)
                )
            except Exception as e:
                logger.error(f"Error sending to next executor: {e}")
        await message.answer(f"✅ Этап завершён! Задача #{ticket_id} передана следующему исполнителю.")


@router.callback_query(F.data.startswith("ticket:needinfo:"))
async def ticket_need_info(
    callback: CallbackQuery,
    db: AsyncSession,
    current_user: User | None = None,
    is_executor: bool = False,
    state: FSMContext = None,
):
    if not is_executor:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    await state.update_data(pending_ticket_id=ticket_id)
    await callback.message.answer(
        "❓ Какую информацию вы запрашиваете у пользователя?",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(ExecutorStates.waiting_info_request)
    await callback.answer()


@router.message(ExecutorStates.waiting_info_request)
async def process_info_request(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User | None = None,
):
    data = await state.get_data()
    ticket_id = data.get("pending_ticket_id")
    await state.clear()

    ticket = await _get_ticket(db, ticket_id)
    if not ticket:
        await message.answer("Заявка не найдена.")
        return

    ticket.status = TicketStatus.waiting_info
    await db.commit()

    creator = await _get_user(db, ticket.creator_id)
    if creator:
        await notify_user_ticket_status(
            message.bot, creator, ticket,
            f"❓ <b>Исполнитель запрашивает информацию по заявке #{ticket_id}</b>\n\n"
            f"{message.text}\n\nОтветьте на этот вопрос, написав боту."
        )

    await message.answer(f"✅ Запрос информации отправлен пользователю.")


@router.callback_query(F.data.startswith("ticket:comment:"))
async def ticket_comment(
    callback: CallbackQuery,
    db: AsyncSession,
    is_executor: bool = False,
    state: FSMContext = None,
):
    if not is_executor:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    await state.update_data(pending_ticket_id=ticket_id, pending_action="comment")
    await callback.message.answer(
        "💬 Введите текст комментария:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(ExecutorStates.waiting_comment)
    await callback.answer()


@router.callback_query(F.data.startswith("ticket:transfer:"))
async def ticket_transfer(
    callback: CallbackQuery,
    db: AsyncSession,
    is_executor: bool = False,
    state: FSMContext = None,
):
    if not is_executor:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[2])
    await state.update_data(pending_ticket_id=ticket_id)

    result = await db.execute(
        select(User).where(
            User.role.in_([UserRole.executor, UserRole.admin]),
            User.is_active == True
        )
    )
    executors = result.scalars().all()

    text = "🔄 Доступные исполнители:\n\n"
    for ex in executors:
        text += f"• {ex.full_name} (ID: {ex.telegram_id})\n"
    text += "\nВведите Telegram ID исполнителя:"

    await callback.message.answer(text, reply_markup=cancel_keyboard())
    await state.set_state(ExecutorStates.waiting_transfer_id)
    await callback.answer()


@router.message(ExecutorStates.waiting_transfer_id)
async def process_transfer(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User | None = None,
):
    data = await state.get_data()
    ticket_id = data.get("pending_ticket_id")
    await state.clear()

    try:
        target_tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("Неверный ID. Введите числовой Telegram ID.")
        return

    result = await db.execute(select(User).where(User.telegram_id == target_tg_id))
    target = result.scalar_one_or_none()

    if not target:
        await message.answer("Пользователь с таким ID не найден в системе.")
        return

    ticket = await _get_ticket(db, ticket_id)
    if not ticket:
        await message.answer("Заявка не найдена.")
        return

    ticket.assignee_id = target.id
    await db.commit()

    creator = await _get_user(db, ticket.creator_id)
    if creator:
        await notify_executor_ticket_transferred(message.bot, target, ticket, creator)

    try:
        await message.bot.send_message(
            target.telegram_id,
            f"📋 Задача #{ticket.id} передана вам:",
            reply_markup=executor_ticket_keyboard(ticket.id)
        )
    except Exception as e:
        logger.error(f"Transfer notify error: {e}")

    await message.answer(f"✅ Задача #{ticket_id} передана {target.full_name}.")


async def _get_ticket(db: AsyncSession, ticket_id: int) -> Ticket | None:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    return result.scalar_one_or_none()


async def _get_user(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
