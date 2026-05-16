"""Конфигурация брендинга рабочего пространства."""

import json
import re
from typing import Optional

from ai_office.core.models import Workspace


# Patterns that are dangerous in custom CSS and must be stripped
_DANGEROUS_CSS_PATTERNS = [
    re.compile(r"expression\s*\(", re.IGNORECASE),
    re.compile(r"url\s*\(", re.IGNORECASE),
    re.compile(r"@import", re.IGNORECASE),
    re.compile(r"behavior\s*:", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"-moz-binding", re.IGNORECASE),
]


def sanitize_css(css: str) -> str:
    """Strip dangerous CSS patterns that could enable XSS attacks.

    Removes: expression(), url(), @import, behavior:, javascript:, -moz-binding.
    """
    if not css:
        return css
    sanitized = css
    for pattern in _DANGEROUS_CSS_PATTERNS:
        sanitized = pattern.sub("", sanitized)
    return sanitized


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
        # Sanitize custom_css before persisting
        if "custom_css" in updates:
            updates["custom_css"] = sanitize_css(updates["custom_css"])
        branding.update(updates)
        settings["branding"] = branding
        workspace.settings_json = json.dumps(settings, ensure_ascii=False)
