"""
User handlers: AI-Interview ticket creation flow.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.user import User, UserRole
from app.db.models.ticket import Ticket, TicketStatus
from app.services.ai_service import process_ticket_interview
from app.services.routing_service import assign_ticket
from app.services.notification import notify_executor_new_ticket, notify_user_ticket_created
from app.bot.keyboards.inline import executor_ticket_keyboard, cancel_keyboard

logger = logging.getLogger(__name__)
router = Router()


class TicketCreationStates(StatesGroup):
    interviewing = State()


@router.message(
    F.text,
    ~F.text.startswith("/"),
)
async def handle_text_message(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User | None = None,
    is_registered: bool = False,
):
    if not is_registered or not current_user:
        await message.answer(
            "👋 Добро пожаловать! Для начала работы напишите /start"
        )
        return

    current_state = await state.get_state()

    if current_state == TicketCreationStates.interviewing:
        await continue_interview(message, state, db, current_user)
        return

    await start_interview(message, state, db, current_user)


async def start_interview(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User,
):
    user_text = message.text.strip()
    history = [{"role": "user", "content": user_text}]
    result = await process_ticket_interview(history, clarification_count=0)

    if result["ready"]:
        await create_ticket_from_result(message, state, db, current_user, history, result)
    else:
        await state.set_state(TicketCreationStates.interviewing)
        await state.update_data(history=history, clarification_count=1)
        await message.answer(f"🤔 {result['question']}", reply_markup=cancel_keyboard())


async def continue_interview(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User,
):
    data = await state.get_data()
    history: list = data.get("history", [])
    clarification_count: int = data.get("clarification_count", 0)

    user_answer = message.text.strip()
    history.append({"role": "user", "content": user_answer})
    result = await process_ticket_interview(history, clarification_count=clarification_count)

    if result["ready"]:
        await create_ticket_from_result(message, state, db, current_user, history, result)
    else:
        history.append({"role": "assistant", "content": result["question"]})
        await state.update_data(history=history, clarification_count=clarification_count + 1)
        await message.answer(f"🤔 {result['question']}", reply_markup=cancel_keyboard())


async def create_ticket_from_result(
    message: Message,
    state: FSMContext,
    db: AsyncSession,
    current_user: User,
    history: list,
    ai_result: dict,
):
    await state.clear()

    description_parts = [m["content"] for m in history if m["role"] == "user"]
    description = "\n".join(description_parts)

    ticket = Ticket(
        title=ai_result.get("title", "Новая заявка"),
        description=description,
        status=TicketStatus.new,
        priority=ai_result.get("priority", "normal"),
        scenario_key=ai_result.get("scenario_key", "default"),
        ai_entities=ai_result.get("entities", {}),
        creator_id=current_user.id,
        workflow_step=0,
    )
    db.add(ticket)
    await db.flush()

    executor = await assign_ticket(db, ticket)
    await db.commit()

    bot = message.bot
    await notify_user_ticket_created(bot, current_user, ticket)

    priority_emoji = {"low": "🟢", "normal": "🔵", "high": "🟠", "critical": "🔴"}
    p_emoji = priority_emoji.get(ticket.priority, "🔵")

    await message.answer(
        f"✅ <b>Заявка #{ticket.id} создана!</b>\n\n"
        f"📝 Тема: {ticket.title}\n"
        f"{p_emoji} Приоритет: {ticket.priority}\n"
        f"🔧 Тип: {ticket.scenario_key}\n\n"
        f"{'Назначен исполнитель: ' + executor.full_name if executor else 'Ожидает назначения исполнителя.'}",
        parse_mode="HTML"
    )

    if executor:
        await notify_executor_new_ticket(bot, executor, ticket, current_user)
        try:
            await bot.send_message(
                executor.telegram_id,
                f"📋 Задача #{ticket.id}:",
                reply_markup=executor_ticket_keyboard(ticket.id)
            )
        except Exception as e:
            logger.error(f"Error sending keyboard to executor: {e}")
