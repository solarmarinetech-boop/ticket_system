from sqlalchemy import BigInteger, String, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
import enum


class UserRole(str, enum.Enum):
    user = "user"
    executor = "executor"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.user, nullable=False
    )
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    # Web console password (for admin login, hashed)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    created_tickets: Mapped[list["Ticket"]] = relationship(  # noqa
        "Ticket", foreign_keys="Ticket.creator_id", back_populates="creator"
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(  # noqa
        "Ticket", foreign_keys="Ticket.assignee_id", back_populates="assignee"
    )

    def __repr__(self):
        return f"<User {self.telegram_id} {self.full_name} [{self.role}]>"
