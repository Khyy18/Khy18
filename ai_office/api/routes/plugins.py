"""Эндпоинты для управления плагинами."""

from typing import Any, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_office.plugins.loader import get_loaded_plugins, reload_plugins

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("", response_model=List[dict[str, Any]])
async def list_plugins():
    """Получить список загруженных плагинов."""
    return get_loaded_plugins()


@router.post("/reload")
async def reload_all_plugins(request: Request):
    """Перезагрузить все плагины (только для owner)."""
    user_role = getattr(request.state, "user_role", "viewer")
    if user_role != "owner":
        return JSONResponse(
            status_code=403,
            content={"detail": "Только владелец может перезагружать плагины"},
        )

    plugins = reload_plugins()
    return {"status": "ok", "plugins": plugins}
