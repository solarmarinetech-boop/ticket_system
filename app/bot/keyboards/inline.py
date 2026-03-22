from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def executor_ticket_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    """Keyboard for executor when receiving/managing a ticket."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="▶️ Взять в работу", callback_data=f"ticket:start:{ticket_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data=f"ticket:done:{ticket_id}"),
        InlineKeyboardButton(text="❓ Нужна инфо", callback_data=f"ticket:needinfo:{ticket_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Передать", callback_data=f"ticket:transfer:{ticket_id}"),
        InlineKeyboardButton(text="💬 Комментарий", callback_data=f"ticket:comment:{ticket_id}"),
    )
    return builder.as_markup()


def ticket_in_progress_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    """Keyboard when ticket is in progress."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data=f"ticket:done:{ticket_id}"),
        InlineKeyboardButton(text="❓ Нужна инфо", callback_data=f"ticket:needinfo:{ticket_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Передать", callback_data=f"ticket:transfer:{ticket_id}"),
        InlineKeyboardButton(text="💬 Комментарий", callback_data=f"ticket:comment:{ticket_id}"),
    )
    return builder.as_markup()


def user_my_tickets_keyboard(tickets: list) -> InlineKeyboardMarkup:
    """Show list of user's tickets."""
    builder = InlineKeyboardBuilder()
    status_emoji = {
        "new": "🆕", "in_progress": "⚙️",
        "waiting_info": "❓", "closed": "✅", "escalated": "⬆️"
    }
    for ticket in tickets[:10]:
        emoji = status_emoji.get(ticket.status, "📋")
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} #{ticket.id} {ticket.title[:30]}",
                callback_data=f"myticket:{ticket.id}"
            )
        )
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def confirm_keyboard(action: str, ticket_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm:{action}:{ticket_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel"),
    )
    return builder.as_markup()
