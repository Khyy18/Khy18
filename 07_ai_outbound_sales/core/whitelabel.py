from __future__ import annotations
"""White-label branding configuration for multi-tenant support."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# Default branding constants
DEFAULT_LOGO_URL = "/static/images/logo.png"
DEFAULT_PRIMARY_COLOR = "#2563eb"
DEFAULT_SECONDARY_COLOR = "#1e40af"
DEFAULT_COMPANY_NAME = "AI Outbound Agency"
DEFAULT_FAVICON_URL = "/static/images/favicon.ico"


class WhitelabelConfig(BaseModel):
    """Schema for tenant brand settings."""

    logo_url: str = DEFAULT_LOGO_URL
    primary_color: str = DEFAULT_PRIMARY_COLOR
    secondary_color: str = DEFAULT_SECONDARY_COLOR
    company_name: str = DEFAULT_COMPANY_NAME
    custom_domain: Optional[str] = None
    favicon_url: str = DEFAULT_FAVICON_URL


def resolve_branding(brand_settings: dict | None) -> WhitelabelConfig:
    """Resolve tenant branding from stored brand_settings dict.

    Args:
        brand_settings: The brand_settings JSONB data from the Tenant model.

    Returns:
        WhitelabelConfig with resolved values (defaults applied where missing).
    """
    if not brand_settings:
        return WhitelabelConfig()
    return WhitelabelConfig(**{k: v for k, v in brand_settings.items() if v is not None})
