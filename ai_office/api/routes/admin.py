"""Эндпоинты административной панели."""

from typing import Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import (
    AdminAgentUpdate,
    IntegrationTestRequest,
    IntegrationTestResponse,
    SystemSettingResponse,
    SystemSettingUpdate,
    WorkspaceResponse,
)
from ai_office.core.database import get_session
from ai_office.core.models import Agent, SystemSetting, Workspace

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _check_owner(request: Request) -> None:
    """Проверка, что пользователь является владельцем."""
    user_role = getattr(request.state, "user_role", "viewer")
    if user_role != "owner":
        raise HTTPException(status_code=403, detail="Доступ только для владельца")


@router.get("/settings", response_model=List[SystemSettingResponse])
async def list_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Получить все системные настройки."""
    _check_owner(request)
    result = await session.execute(select(SystemSetting))
    settings = result.scalars().all()
    return [SystemSettingResponse.model_validate(s) for s in settings]


@router.patch("/settings")
async def update_settings(
    request: Request,
    updates: Dict[str, str],
    session: AsyncSession = Depends(get_session),
):
    """Обновить системные настройки (словарь ключ-значение)."""
    _check_owner(request)
    for key, value in updates.items():
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            session.add(setting)
    await session.commit()
    return {"status": "ok", "updated": list(updates.keys())}


@router.patch("/agents/{name}")
async def update_agent(
    name: str,
    data: AdminAgentUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Обновить системный промпт или статус агента."""
    _check_owner(request)
    result = await session.execute(
        select(Agent).where(Agent.name == name)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    if data.system_prompt is not None:
        agent.system_prompt = data.system_prompt
    if data.enabled is not None:
        agent.status = "idle" if data.enabled else "disabled"

    await session.commit()
    await session.refresh(agent)
    return {"status": "ok", "agent": agent.name, "agent_status": agent.status}


@router.post("/integrations/test", response_model=IntegrationTestResponse)
async def test_integration(
    data: IntegrationTestRequest,
    request: Request,
):
    """Тестировать подключение к внешней интеграции (Linear/Notion)."""
    _check_owner(request)

    if data.integration_type == "linear":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.linear.app/graphql",
                    headers={"Authorization": data.api_key},
                    json={"query": "{ viewer { id name } }"},
                )
                if resp.status_code == 200 and "data" in resp.json():
                    return IntegrationTestResponse(
                        success=True, message="Linear подключен успешно"
                    )
                return IntegrationTestResponse(
                    success=False, message="Неверный API ключ Linear"
                )
        except Exception as e:
            return IntegrationTestResponse(
                success=False, message=f"Ошибка подключения к Linear: {str(e)}"
            )

    elif data.integration_type == "notion":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.notion.com/v1/users/me",
                    headers={
                        "Authorization": f"Bearer {data.api_key}",
                        "Notion-Version": "2022-06-28",
                    },
                )
                if resp.status_code == 200:
                    return IntegrationTestResponse(
                        success=True, message="Notion подключен успешно"
                    )
                return IntegrationTestResponse(
                    success=False, message="Неверный API ключ Notion"
                )
        except Exception as e:
            return IntegrationTestResponse(
                success=False, message=f"Ошибка подключения к Notion: {str(e)}"
            )

    return IntegrationTestResponse(
        success=False, message=f"Неизвестный тип интеграции: {data.integration_type}"
    )


@router.get("/workspaces", response_model=List[WorkspaceResponse])
async def list_workspaces(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Получить список всех рабочих пространств."""
    _check_owner(request)
    result = await session.execute(select(Workspace))
    workspaces = result.scalars().all()
    return [WorkspaceResponse.model_validate(w) for w in workspaces]
