"""Инструменты планирования - многошаговые планы."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent, Plan, PlanStep


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Alice."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Alice")
        )
        agent = result.scalar_one_or_none()
        if agent:
            log = ActivityLog(
                agent_id=agent.id,
                action_type=action_type,
                action_description=description,
            )
            session.add(log)
            await session.commit()


@tool
async def create_plan(goal: str, steps: str) -> str:
    """Создать план с пошаговым выполнением.

    Args:
        goal: Цель плана
        steps: Шаги плана через запятую (например: "Анализ требований, Дизайн, Разработка, Тестирование")

    Returns:
        Подтверждение создания плана с ID и списком шагов
    """
    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    if not step_list:
        return "Ошибка: необходимо указать хотя бы один шаг плана."

    async with async_session() as session:
        plan = Plan(goal=goal, status="active")
        session.add(plan)
        await session.flush()

        for i, step_desc in enumerate(step_list, 1):
            step = PlanStep(
                plan_id=plan.id,
                step_number=i,
                description=step_desc,
                status="pending",
            )
            session.add(step)

        await session.commit()

        lines = [f"План создан (ID: {plan.id})"]
        lines.append(f"Цель: {goal}")
        lines.append(f"Шаги ({len(step_list)}):")
        for i, step_desc in enumerate(step_list, 1):
            lines.append(f"  {i}. {step_desc}")

    await _log_activity("plan_created", f"Создан план: {goal} ({len(step_list)} шагов)")
    return "\n".join(lines)


@tool
async def execute_next_step(plan_id: int) -> str:
    """Выполнить следующий шаг плана.

    Args:
        plan_id: ID плана

    Returns:
        Описание выполненного шага и информация о следующем
    """
    async with async_session() as session:
        result = await session.execute(
            select(Plan).where(Plan.id == plan_id)
        )
        plan = result.scalar_one_or_none()
        if not plan:
            return f"План #{plan_id} не найден."

        if plan.status == "completed":
            return f"План #{plan_id} уже завершён."

        # Находим первый pending шаг
        result = await session.execute(
            select(PlanStep)
            .where(PlanStep.plan_id == plan_id, PlanStep.status == "pending")
            .order_by(PlanStep.step_number)
        )
        pending_step = result.scalar_one_or_none()

        if not pending_step:
            plan.status = "completed"
            await session.commit()
            return f"Все шаги плана #{plan_id} выполнены. План завершён."

        pending_step.status = "done"
        await session.flush()

        # Проверяем, есть ли следующий шаг
        result = await session.execute(
            select(PlanStep)
            .where(PlanStep.plan_id == plan_id, PlanStep.status == "pending")
            .order_by(PlanStep.step_number)
        )
        next_step = result.scalar_one_or_none()

        lines = [f"Выполнен шаг {pending_step.step_number}: {pending_step.description}"]
        if next_step:
            lines.append(f"Следующий шаг {next_step.step_number}: {next_step.description}")
        else:
            plan.status = "completed"
            lines.append("Это был последний шаг. План завершён!")

        await session.commit()

    await _log_activity("plan_step_executed", f"Выполнен шаг плана #{plan_id}")
    return "\n".join(lines)


@tool
async def get_plan_status(plan_id: int) -> str:
    """Получить статус плана с прогрессом выполнения.

    Args:
        plan_id: ID плана

    Returns:
        Форматированный статус плана с прогрессом
    """
    async with async_session() as session:
        result = await session.execute(
            select(Plan).where(Plan.id == plan_id)
        )
        plan = result.scalar_one_or_none()
        if not plan:
            return f"План #{plan_id} не найден."

        result = await session.execute(
            select(PlanStep)
            .where(PlanStep.plan_id == plan_id)
            .order_by(PlanStep.step_number)
        )
        steps = result.scalars().all()

        total = len(steps)
        done = sum(1 for s in steps if s.status == "done")
        percentage = int((done / total) * 100) if total > 0 else 0

        status_icons = {"done": "[x]", "in_progress": "[~]", "pending": "[ ]"}

        lines = [f"План #{plan_id}: {plan.goal}"]
        lines.append(f"Статус: {plan.status} | Прогресс: {done}/{total} ({percentage}%)")
        lines.append("Шаги:")
        for step in steps:
            icon = status_icons.get(step.status, "[ ]")
            lines.append(f"  {icon} {step.step_number}. {step.description}")

    await _log_activity("plan_status_checked", f"Проверен статус плана #{plan_id}")
    return "\n".join(lines)
