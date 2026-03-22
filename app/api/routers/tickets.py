"""
Tickets CRUD API for Web Console.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional
from datetime import datetime

from app.db.session import get_db
from app.db.models.ticket import Ticket, TicketStatus, TicketPriority, TicketComment
from app.db.models.user import User
from app.api.routers.auth import get_current_admin

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


class TicketResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str
    scenario_key: str | None
    workflow_step: int
    creator_id: int
    assignee_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_telegram_id: Optional[int] = None


@router.get("/", response_model=list[TicketResponse])
async def list_tickets(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    filters = []
    if status:
        filters.append(Ticket.status == status)
    if priority:
        filters.append(Ticket.priority == priority)
    if assignee_id:
        filters.append(Ticket.assignee_id == assignee_id)

    query = select(Ticket)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: int,
    update: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if update.status:
        try:
            ticket.status = TicketStatus(update.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")

    if update.priority:
        try:
            ticket.priority = TicketPriority(update.priority)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid priority")

    if update.assignee_telegram_id is not None:
        user_result = await db.execute(
            select(User).where(User.telegram_id == update.assignee_telegram_id)
        )
        assignee = user_result.scalar_one_or_none()
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
        ticket.assignee_id = assignee.id

    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/{ticket_id}/comments")
async def get_comments(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(TicketComment)
        .where(TicketComment.ticket_id == ticket_id)
        .order_by(TicketComment.created_at)
    )
    return result.scalars().all()
