"""Менеджер маркетплейса плагинов."""

import json
import os
from typing import Optional


class MarketplaceManager:
    """Управление маркетплейсом плагинов."""

    def __init__(self):
        self._installed: set[str] = set()
        self._registry_path = os.path.join(
            os.path.dirname(__file__), "plugins_registry.json"
        )

    def list_available_plugins(self) -> list[dict]:
        """Получить список доступных плагинов из реестра."""
        try:
            with open(self._registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def install_plugin(self, plugin_id: str) -> Optional[dict]:
        """Установить плагин (пометить как установленный)."""
        plugins = self.list_available_plugins()
        for plugin in plugins:
            if plugin["id"] == plugin_id:
                self._installed.add(plugin_id)
                return plugin
        return None

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """Удалить плагин (пометить как удалённый)."""
        if plugin_id in self._installed:
            self._installed.discard(plugin_id)
            return True
        return False

    def is_installed(self, plugin_id: str) -> bool:
        """Проверить установлен ли плагин."""
        return plugin_id in self._installed


# Module-level instance
marketplace_manager = MarketplaceManager()
