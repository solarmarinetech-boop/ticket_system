"""
Users management API for Web Console.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime

from app.db.session import get_db
from app.db.models.user import User, UserRole
from app.db.models.route import WorkflowScenario, WorkflowStep
from app.api.routers.auth import get_current_admin, get_password_hash

users_router = APIRouter(prefix="/api/users", tags=["users"])
routes_router = APIRouter(prefix="/api/routes", tags=["routes"])


# ─── Users ────────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: int
    telegram_id: int
    full_name: str
    department: str | None
    role: str
    username: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    hashed_password: Optional[str] = None
    new_password: Optional[str] = None


@users_router.get("/", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    return result.scalars().all()


@users_router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if update.role:
        try:
            user.role = UserRole(update.role)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid role")

    if update.is_active is not None:
        user.is_active = update.is_active

    if update.new_password:
        user.hashed_password = get_password_hash(update.new_password)

    await db.commit()
    await db.refresh(user)
    return user


# ─── Workflow Routes ───────────────────────────────────────────────────────────

class StepIn(BaseModel):
    order: int
    executor_telegram_id: Optional[int] = None
    role_fallback: Optional[str] = None
    task_description: Optional[str] = None


class ScenarioIn(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    steps: list[StepIn]


class ScenarioResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    is_active: bool

    class Config:
        from_attributes = True


@routes_router.get("/", response_model=list[ScenarioResponse])
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(select(WorkflowScenario).order_by(WorkflowScenario.key))
    return result.scalars().all()


@routes_router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(WorkflowScenario).where(WorkflowScenario.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    steps_result = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.scenario_id == scenario_id)
        .order_by(WorkflowStep.order)
    )
    steps = steps_result.scalars().all()

    return {
        "id": scenario.id,
        "key": scenario.key,
        "name": scenario.name,
        "description": scenario.description,
        "is_active": scenario.is_active,
        "steps": [
            {
                "id": s.id,
                "order": s.order,
                "executor_id": s.executor_id,
                "role_fallback": s.role_fallback,
                "task_description": s.task_description,
            }
            for s in steps
        ]
    }


@routes_router.post("/")
async def create_scenario(
    data: ScenarioIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    scenario = WorkflowScenario(
        key=data.key,
        name=data.name,
        description=data.description,
    )
    db.add(scenario)
    await db.flush()

    for step_data in data.steps:
        executor_id = None
        if step_data.executor_telegram_id:
            result = await db.execute(
                select(User).where(User.telegram_id == step_data.executor_telegram_id)
            )
            executor = result.scalar_one_or_none()
            if executor:
                executor_id = executor.id

        step = WorkflowStep(
            scenario_id=scenario.id,
            order=step_data.order,
            executor_id=executor_id,
            role_fallback=step_data.role_fallback,
            task_description=step_data.task_description,
        )
        db.add(step)

    await db.commit()
    return {"id": scenario.id, "key": scenario.key}


@routes_router.delete("/{scenario_id}")
async def delete_scenario(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(WorkflowScenario).where(WorkflowScenario.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(scenario)
    await db.commit()
    return {"ok": True}
