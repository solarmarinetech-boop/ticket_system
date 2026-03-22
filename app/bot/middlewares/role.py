"""
Role middleware — loads current user from DB and attaches to handler data.
"""
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.user import User, UserRole
from app.config import settings

logger = logging.getLogger(__name__)


class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Get telegram user
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
        
        if tg_user is None:
            return await handler(event, data)
        
        db: AsyncSession = data.get("db")
        if not db:
            return await handler(event, data)
        
        # Load user from DB
        result = await db.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()
        
        # Auto-promote admins defined in ENV
        if user and tg_user.id in settings.admin_ids_list:
            if user.role != UserRole.admin:
                user.role = UserRole.admin
                await db.commit()
        
        data["current_user"] = user
        data["is_registered"] = user is not None
        data["is_executor"] = user is not None and user.role in (UserRole.executor, UserRole.admin)
        data["is_admin"] = user is not None and user.role == UserRole.admin
        
        return await handler(event, data)
