"""
Routing Service — assigns executors based on workflow scenarios.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.route import WorkflowScenario, WorkflowStep
from app.db.models.ticket import Ticket, TicketStatus
from app.db.models.user import User, UserRole

logger = logging.getLogger(__name__)


async def get_scenario(db: AsyncSession, key: str) -> WorkflowScenario | None:
    result = await db.execute(
        select(WorkflowScenario)
        .where(WorkflowScenario.key == key, WorkflowScenario.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_step(db: AsyncSession, scenario: WorkflowScenario, step_index: int) -> WorkflowStep | None:
    result = await db.execute(
        select(WorkflowStep)
        .where(
            WorkflowStep.scenario_id == scenario.id,
            WorkflowStep.order == step_index,
        )
    )
    return result.scalar_one_or_none()


async def assign_ticket(db: AsyncSession, ticket: Ticket) -> User | None:
    """
    Assign ticket to the correct executor based on scenario + current step.
    Returns the assigned User or None if no executor found.
    """
    scenario_key = ticket.scenario_key or "default"
    scenario = await get_scenario(db, scenario_key)
    
    if not scenario:
        scenario = await get_scenario(db, "default")
    
    if not scenario:
        logger.warning(f"No scenario found for key: {scenario_key}")
        return await _assign_to_admin(db)
    
    step = await get_step(db, scenario, ticket.workflow_step)
    
    if not step:
        # No more steps — ticket is done
        return None
    
    executor = None
    
    if step.executor_id:
        result = await db.execute(select(User).where(User.id == step.executor_id))
        executor = result.scalar_one_or_none()
    
    if not executor and step.role_fallback:
        executor = await _find_by_role(db, step.role_fallback)
    
    if executor:
        ticket.assignee_id = executor.id
        await db.commit()
        logger.info(f"Ticket #{ticket.id} assigned to {executor.full_name} (step {ticket.workflow_step})")
    
    return executor


async def advance_ticket(db: AsyncSession, ticket: Ticket) -> tuple[User | None, bool]:
    """
    Move ticket to next workflow step.
    Returns (next_executor, is_finished).
    """
    scenario_key = ticket.scenario_key or "default"
    scenario = await get_scenario(db, scenario_key)
    
    if not scenario:
        # No scenario — close it
        ticket.status = TicketStatus.closed
        await db.commit()
        return None, True
    
    next_step_index = ticket.workflow_step + 1
    next_step = await get_step(db, scenario, next_step_index)
    
    if not next_step:
        # End of chain
        ticket.status = TicketStatus.closed
        ticket.workflow_step = next_step_index
        await db.commit()
        return None, True
    
    # Move to next step
    ticket.workflow_step = next_step_index
    ticket.status = TicketStatus.new
    await db.commit()
    
    executor = await assign_ticket(db, ticket)
    return executor, False


async def _assign_to_admin(db: AsyncSession) -> User | None:
    result = await db.execute(
        select(User).where(User.role == UserRole.admin, User.is_active == True).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_by_role(db: AsyncSession, role_str: str) -> User | None:
    try:
        role = UserRole(role_str)
    except ValueError:
        return None
    result = await db.execute(
        select(User).where(User.role == role, User.is_active == True).limit(1)
    )
    return result.scalar_one_or_none()


async def seed_default_scenarios(db: AsyncSession):
    """Insert default workflow scenarios if they don't exist."""
    scenarios = [
        {
            "key": "new_hire",
            "name": "Новый сотрудник",
            "description": "Подключение нового сотрудника",
            "steps": [
                {"order": 0, "task_description": "Создать учётную запись"},
                {"order": 1, "task_description": "Настроить почту"},
                {"order": 2, "task_description": "Установить ПО и выдать оборудование"},
            ]
        },
        {
            "key": "hardware_fail",
            "name": "Сломалось оборудование",
            "description": "Поломка или замена оборудования",
            "steps": [
                {"order": 0, "task_description": "Выдать новое оборудование / устранить поломку"},
            ]
        },
        {
            "key": "software",
            "name": "Проблема с ПО",
            "description": "Установка или настройка программного обеспечения",
            "steps": [
                {"order": 0, "task_description": "Установить / настроить ПО"},
            ]
        },
        {
            "key": "access",
            "name": "Доступ к системам",
            "description": "Предоставление доступа, сброс пароля",
            "steps": [
                {"order": 0, "task_description": "Предоставить доступ / сбросить пароль"},
            ]
        },
        {
            "key": "network",
            "name": "Проблемы с сетью",
            "description": "Интернет, VPN, сетевые ресурсы",
            "steps": [
                {"order": 0, "task_description": "Устранить сетевую проблему"},
            ]
        },
        {
            "key": "default",
            "name": "Общая заявка",
            "description": "Неизвестная проблема — сортировка администратором",
            "steps": [
                {"order": 0, "role_fallback": "admin", "task_description": "Определить исполнителя"},
            ]
        },
    ]

    for s_data in scenarios:
        existing = await get_scenario(db, s_data["key"])
        if existing:
            continue
        scenario = WorkflowScenario(
            key=s_data["key"],
            name=s_data["name"],
            description=s_data.get("description"),
        )
        db.add(scenario)
        await db.flush()
        for step_data in s_data["steps"]:
            step = WorkflowStep(
                scenario_id=scenario.id,
                order=step_data["order"],
                task_description=step_data.get("task_description"),
                role_fallback=step_data.get("role_fallback"),
            )
            db.add(step)
    await db.commit()
    logger.info("Default workflow scenarios seeded.")
