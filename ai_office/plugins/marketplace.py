"""Менеджер маркетплейса плагинов."""

import json
import os
from typing import Optional


class MarketplaceManager:
    """Управление маркетплейсом плагинов."""

    def __init__(self):
        self._registry_path = os.path.join(
            os.path.dirname(__file__), "plugins_registry.json"
        )
        self._installed_path = os.path.join(
            os.path.dirname(__file__), ".installed.json"
        )
        self._installed: set[str] = self._load_installed()

    def _load_installed(self) -> set[str]:
        """Load installed plugin IDs from disk."""
        try:
            with open(self._installed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return set()

    def _save_installed(self) -> None:
        """Persist installed plugin IDs to disk."""
        with open(self._installed_path, "w", encoding="utf-8") as f:
            json.dump(sorted(self._installed), f, ensure_ascii=False)

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
                self._save_installed()
                return plugin
        return None

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """Удалить плагин (пометить как удалённый)."""
        if plugin_id in self._installed:
            self._installed.discard(plugin_id)
            self._save_installed()
            return True
        return False

    def is_installed(self, plugin_id: str) -> bool:
        """Проверить установлен ли плагин."""
        return plugin_id in self._installed


# Module-level instance
marketplace_manager = MarketplaceManager()
