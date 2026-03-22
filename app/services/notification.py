"""
Notification Service — sends Telegram messages to users and executors.
"""
import logging
from aiogram import Bot
from app.db.models.ticket import Ticket
from app.db.models.user import User

logger = logging.getLogger(__name__)


async def notify_executor_new_ticket(bot: Bot, executor: User, ticket: Ticket, creator: User):
    """Notify executor about a new task assigned to them."""
    priority_emoji = {"low": "🟢", "normal": "🔵", "high": "🟠", "critical": "🔴"}
    emoji = priority_emoji.get(ticket.priority, "🔵")
    
    text = (
        f"📋 <b>Новая задача #{ticket.id}</b>\n\n"
        f"{emoji} Приоритет: <b>{ticket.priority}</b>\n"
        f"👤 От: <b>{creator.full_name}</b> ({creator.department or 'отдел не указан'})\n"
        f"📝 Тема: <b>{ticket.title}</b>\n\n"
        f"<i>{ticket.description[:500]}</i>"
    )
    try:
        await bot.send_message(executor.telegram_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify executor {executor.telegram_id}: {e}")


async def notify_user_ticket_created(bot: Bot, user: User, ticket: Ticket):
    """Notify user that their ticket was created."""
    text = (
        f"✅ <b>Заявка #{ticket.id} создана!</b>\n\n"
        f"📝 Тема: <b>{ticket.title}</b>\n"
        f"⏳ Статус: <b>В обработке</b>\n\n"
        f"Я уведомлю вас об изменениях. Вы можете проверить статус командой /mystatus"
    )
    try:
        await bot.send_message(user.telegram_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify user {user.telegram_id}: {e}")


async def notify_user_ticket_closed(bot: Bot, user: User, ticket: Ticket, comment: str = None):
    """Notify user that their ticket is closed."""
    text = (
        f"✅ <b>Заявка #{ticket.id} выполнена!</b>\n\n"
        f"📝 Тема: {ticket.title}\n"
    )
    if comment:
        text += f"\n💬 Комментарий исполнителя:\n<i>{comment}</i>"
    
    text += "\n\nЕсли проблема не решена — создайте новую заявку."
    try:
        await bot.send_message(user.telegram_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify user {user.telegram_id}: {e}")


async def notify_user_ticket_status(bot: Bot, user: User, ticket: Ticket, message: str):
    """Generic status update notification."""
    try:
        await bot.send_message(user.telegram_id, message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify user {user.telegram_id}: {e}")


async def notify_executor_ticket_transferred(bot: Bot, executor: User, ticket: Ticket, from_user: User):
    """Notify executor that a ticket was transferred to them."""
    text = (
        f"🔄 <b>Задача #{ticket.id} передана вам</b>\n\n"
        f"📝 Тема: <b>{ticket.title}</b>\n"
        f"👤 Создатель: {from_user.full_name}\n\n"
        f"<i>{ticket.description[:300]}</i>"
    )
    try:
        await bot.send_message(executor.telegram_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify executor {executor.telegram_id}: {e}")
