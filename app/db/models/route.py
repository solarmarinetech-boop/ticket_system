from sqlalchemy import String, Integer, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class WorkflowScenario(Base):
    """
    Defines a named routing scenario, e.g. 'new_hire', 'hardware_fail'.
    Contains an ordered list of executor user IDs.
    """
    __tablename__ = "workflow_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # e.g. "new_hire"
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # Human-readable
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    steps: Mapped[list["WorkflowStep"]] = relationship(
        "WorkflowStep", back_populates="scenario",
        order_by="WorkflowStep.order",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<WorkflowScenario {self.key}>"


class WorkflowStep(Base):
    """
    A single step in a workflow: which executor handles it and what they do.
    """
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("workflow_scenarios.id"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-indexed step order
    executor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    role_fallback: Mapped[str] = mapped_column(String(50), nullable=True)  # e.g. "executor", "admin"
    task_description: Mapped[str] = mapped_column(String(500), nullable=True)

    scenario: Mapped["WorkflowScenario"] = relationship("WorkflowScenario", back_populates="steps")
    executor: Mapped["User"] = relationship("User")  # noqa
