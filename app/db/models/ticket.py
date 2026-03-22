from sqlalchemy import (
    BigInteger, String, Enum, DateTime, Text, ForeignKey, Integer, func, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
import enum


class TicketStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    waiting_info = "waiting_info"
    escalated = "escalated"
    closed = "closed"


class TicketPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus), default=TicketStatus.new, nullable=False
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority), default=TicketPriority.normal, nullable=False
    )

    # Classification
    scenario_key: Mapped[str] = mapped_column(String(100), nullable=True)  # e.g. "new_hire"
    ai_entities: Mapped[dict] = mapped_column(JSON, nullable=True)  # extracted entities

    # Workflow position
    workflow_step: Mapped[int] = mapped_column(Integer, default=0)

    # Relations
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    creator: Mapped["User"] = relationship(  # noqa
        "User", foreign_keys=[creator_id], back_populates="created_tickets"
    )
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    assignee: Mapped["User"] = relationship(  # noqa
        "User", foreign_keys=[assignee_id], back_populates="assigned_tickets"
    )

    # Timestamps
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)

    comments: Mapped[list["TicketComment"]] = relationship(
        "TicketComment", back_populates="ticket", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Ticket #{self.id} [{self.status}] {self.title[:40]}>"


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=True)
    photo_file_id: Mapped[str] = mapped_column(String(200), nullable=True)  # Telegram file_id
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="comments")
    author: Mapped["User"] = relationship("User")  # noqa
