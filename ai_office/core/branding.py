"""Конфигурация брендинга рабочего пространства."""

import json
from typing import Optional

from ai_office.core.models import Workspace


class BrandingConfig:
    """Конфигурация брендинга, хранимая в Workspace.settings_json."""

    DEFAULT = {
        "company_name": "AI Office",
        "logo_url": "",
        "accent_color": "#3b82f6",
        "agent_names": {},
        "enabled_agents": ["alice", "sam", "max", "eva", "leo", "nova", "iris", "oscar"],
        "welcome_message": "",
        "custom_css": "",
    }

    @classmethod
    def from_workspace(cls, workspace: Optional[Workspace]) -> dict:
        """Извлечь конфигурацию брендинга из workspace.settings_json."""
        config = dict(cls.DEFAULT)

        if workspace is None or not workspace.settings_json:
            return config

        try:
            settings = json.loads(workspace.settings_json)
            branding = settings.get("branding", {})
            for key in config:
                if key in branding:
                    config[key] = branding[key]
        except (json.JSONDecodeError, TypeError):
            pass

        return config

    @classmethod
    def update_workspace_branding(cls, workspace: Workspace, updates: dict) -> None:
        """Обновить раздел branding в workspace.settings_json."""
        try:
            settings = json.loads(workspace.settings_json or "{}")
        except (json.JSONDecodeError, TypeError):
            settings = {}

        branding = settings.get("branding", dict(cls.DEFAULT))
        branding.update(updates)
        settings["branding"] = branding
        workspace.settings_json = json.dumps(settings, ensure_ascii=False)
