"""Эндпоинты для маркетплейса плагинов."""

from fastapi import APIRouter, HTTPException

from ai_office.api.schemas import MarketplacePluginResponse
from ai_office.plugins.marketplace import marketplace_manager

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


@router.get("", response_model=list[MarketplacePluginResponse])
async def list_marketplace_plugins():
    """Получить список доступных плагинов."""
    plugins = marketplace_manager.list_available_plugins()
    return [
        MarketplacePluginResponse(
            id=p["id"],
            name=p["name"],
            description=p["description"],
            version=p["version"],
            author=p["author"],
            download_url=p.get("download_url", ""),
            tools_count=p["tools_count"],
            installed=marketplace_manager.is_installed(p["id"]),
        )
        for p in plugins
    ]


@router.post("/install/{plugin_id}", response_model=MarketplacePluginResponse)
async def install_plugin(plugin_id: str):
    """Установить плагин из маркетплейса."""
    plugin = marketplace_manager.install_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="Плагин не найден")
    return MarketplacePluginResponse(
        id=plugin["id"],
        name=plugin["name"],
        description=plugin["description"],
        version=plugin["version"],
        author=plugin["author"],
        download_url=plugin.get("download_url", ""),
        tools_count=plugin["tools_count"],
        installed=True,
    )


@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str):
    """Удалить плагин."""
    success = marketplace_manager.uninstall_plugin(plugin_id)
    if not success:
        raise HTTPException(status_code=404, detail="Плагин не установлен")
    return {"status": "uninstalled", "plugin_id": plugin_id}
