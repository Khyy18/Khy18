"""Загрузчик плагинов для AI Office."""

import importlib
import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from ai_office.agents.base import AgentConfig
from ai_office.agents.registry import registry

logger = logging.getLogger(__name__)

_loaded_plugins: list[dict[str, Any]] = []

PLUGINS_DIR = Path(__file__).parent


def _import_module_from_path(module_name: str, file_path: Path):
    """Импортировать модуль по пути к файлу."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect_tools(module) -> list:
    """Собрать все @tool функции из модуля."""
    from langchain_core.tools import BaseTool

    tools = []
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        if isinstance(attr, BaseTool):
            tools.append(attr)
    return tools


def load_plugins() -> list[dict[str, Any]]:
    """Сканировать директорию плагинов и загрузить все найденные.

    Каждый плагин - это поддиректория с manifest.yaml.
    """
    global _loaded_plugins
    _loaded_plugins = []

    if not PLUGINS_DIR.exists():
        return _loaded_plugins

    for entry in sorted(PLUGINS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("__"):
            continue

        manifest_path = entry / "manifest.yaml"
        if not manifest_path.exists():
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)

            if not manifest or "name" not in manifest:
                logger.warning("Плагин %s: некорректный manifest.yaml", entry.name)
                continue

            # Загружаем инструменты
            tools = []
            tool_modules = manifest.get("tools", [])
            tools_file = entry / "tools.py"

            if tools_file.exists():
                module_name = f"ai_office.plugins.{entry.name}.tools"
                module = _import_module_from_path(module_name, tools_file)
                all_tools = _collect_tools(module)

                # Фильтруем по именам из манифеста если указаны
                if tool_modules:
                    tools = [t for t in all_tools if t.name in tool_modules]
                else:
                    tools = all_tools

            # Создаем AgentConfig и регистрируем
            config = AgentConfig(
                name=manifest["name"],
                role=manifest.get("role", ""),
                system_prompt=manifest.get("system_prompt", ""),
                tools=tools,
                model=manifest.get("model", "gpt-4o-mini"),
            )
            registry.register(config)

            plugin_info = {
                "name": manifest["name"],
                "display_name": manifest.get("display_name", manifest["name"]),
                "role": manifest.get("role", ""),
                "tools": [t.name for t in tools],
            }
            _loaded_plugins.append(plugin_info)
            logger.info("Плагин загружен: %s (%d инструментов)", manifest["name"], len(tools))

        except Exception as e:
            logger.error("Ошибка загрузки плагина %s: %s", entry.name, str(e))

    return _loaded_plugins


def reload_plugins() -> list[dict[str, Any]]:
    """Перезагрузить все плагины.

    Удаляет плагин-агентов из реестра и загружает заново.
    """
    global _loaded_plugins

    # Удаляем только плагин-агентов из реестра
    for plugin in _loaded_plugins:
        name = plugin["name"].lower()
        if name in registry._agents:
            del registry._agents[name]

    _loaded_plugins = []
    return load_plugins()


def get_loaded_plugins() -> list[dict[str, Any]]:
    """Получить список загруженных плагинов."""
    return _loaded_plugins.copy()
