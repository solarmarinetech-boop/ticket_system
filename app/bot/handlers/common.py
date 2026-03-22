"""
Common handlers: /start, registration flow, /help, /mystatus
"""
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.user import User, UserRole
from app.db.models.ticket import Ticket, TicketStatus
from app.bot.keyboards.inline import user_my_tickets_keyboard, cancel_keyboard
from app.config import settings

logger = logging.getLogger(__name__)
router = Router()


class RegistrationStates(StatesGroup):
    waiting_full_name = State()
    waiting_department = State()


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    current_user: User | None = None,
    is_registered: bool = False,
):
    await state.clear()

    if current_user:
        role_name = {"user": "Сотрудник", "executor": "ИТ-сотрудник", "admin": "Администратор"}
        await message.answer(
            f"👋 С возвращением, <b>{current_user.full_name}</b>!\n"
            f"🎭 Ваша роль: {role_name.get(current_user.role, current_user.role)}\n\n"
            f"Напишите описание вашей проблемы, и я помогу создать заявку.\n"
            f"/mystatus — мои заявки\n"
            f"/help — помощь",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "👋 Добро пожаловать в систему ИТ-заявок!\n\n"
        "Для начала работы мне нужны ваши данные.\n"
        "Введите ваше <b>полное имя</b> (ФИО):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_full_name)


@router.message(RegistrationStates.waiting_full_name)
async def process_full_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Пожалуйста, введите корректное имя (минимум 2 символа).")
        return

    await state.update_data(full_name=name)
    await message.answer(
        f"Отлично, <b>{name}</b>! 👍\n\n"
        "Теперь укажите ваш <b>отдел</b> (например: Бухгалтерия, Продажи, HR):",
        parse_mode="HTML"
    )
    await state.set_state(RegistrationStates.waiting_department)


@router.message(RegistrationStates.waiting_department)
async def process_department(
    message: Message, state: FSMContext, db: AsyncSession
):
    department = message.text.strip()
    data = await state.get_data()
    full_name = data.get("full_name", "")
    await state.clear()

    is_env_admin = message.from_user.id in settings.admin_ids_list
    role = UserRole.admin if is_env_admin else UserRole.user

    # Проверяем — вдруг уже зарегистрирован
    result = await db.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one_or_none()

    if user:
        user.full_name = full_name
        user.department = department
        user.role = role
    else:
        user = User(
            telegram_id=message.from_user.id,
            full_name=full_name,
            department=department,
            username=message.from_user.username,
            role=role,
        )
        db.add(user)

    await db.commit()

    extra = "\n\n🔑 Вы зарегистрированы как <b>Администратор</b>." if role == UserRole.admin else ""

    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"👤 Имя: <b>{full_name}</b>\n"
        f"🏢 Отдел: <b>{department}</b>{extra}\n\n"
        f"Теперь просто опишите свою проблему текстом — я создам заявку!",
        parse_mode="HTML"
    )


@router.message(Command("mystatus"))
async def cmd_my_status(
    message: Message,
    db: AsyncSession,
    current_user: User | None = None,
):
    if not current_user:
        await message.answer("Сначала зарегистрируйтесь — напишите /start")
        return

    result = await db.execute(
        select(Ticket)
        .where(
            Ticket.creator_id == current_user.id,
            Ticket.status != TicketStatus.closed
        )
        .order_by(Ticket.created_at.desc())
        .limit(10)
    )
    tickets = result.scalars().all()

    if not tickets:
        await message.answer("У вас нет активных заявок. Напишите описание проблемы — создам заявку!")
        return

    await message.answer(
        f"📋 Ваши активные заявки ({len(tickets)}):",
        reply_markup=user_my_tickets_keyboard(tickets)
    )


@router.callback_query(F.data.startswith("myticket:"))
async def show_my_ticket(
    callback: CallbackQuery,
    db: AsyncSession,
    current_user: User | None = None,
):
    ticket_id = int(callback.data.split(":")[1])
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket or (current_user and ticket.creator_id != current_user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    status_names = {
        "new": "🆕 Новая", "in_progress": "⚙️ В работе",
        "waiting_info": "❓ Ожидает информации",
        "closed": "✅ Закрыта", "escalated": "⬆️ Эскалирована"
    }

    text = (
        f"📋 <b>Заявка #{ticket.id}</b>\n\n"
        f"📝 Тема: {ticket.title}\n"
        f"🔘 Статус: {status_names.get(ticket.status, ticket.status)}\n"
        f"⚡ Приоритет: {ticket.priority}\n"
        f"📅 Создана: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<i>{ticket.description[:400]}</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(
    message: Message,
    current_user: User | None = None,
):
    text = (
        "🤖 <b>Система ИТ-заявок</b>\n\n"
        "📝 Просто напишите описание проблемы — я задам уточняющие вопросы и создам заявку.\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/mystatus — мои заявки\n"
        "/help — эта справка"
    )
    if current_user and current_user.role.value in ("executor", "admin"):
        text += "\n\n<b>Для ИТ-сотрудников:</b>\n/mytasks — мои задачи"
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer()
