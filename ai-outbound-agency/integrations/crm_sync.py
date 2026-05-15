"""CRM synchronization adapters for HubSpot and Pipedrive."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class CRMAdapter(ABC):
    """Abstract base class for CRM integrations."""

    @abstractmethod
    async def push_lead(self, lead_data: dict) -> dict:
        """Push a lead/contact to the CRM.

        Args:
            lead_data: Dictionary with lead information (email, name, company, etc.)

        Returns:
            Dict with CRM record ID and status.
        """
        ...

    @abstractmethod
    async def update_deal_stage(self, deal_id: str, stage: str) -> dict:
        """Update a deal/opportunity stage in the CRM.

        Args:
            deal_id: The CRM deal identifier.
            stage: The new stage name.

        Returns:
            Dict with updated deal info.
        """
        ...

    @abstractmethod
    async def sync_from_crm(self, since: Optional[str] = None) -> list[dict]:
        """Pull recently modified records from the CRM.

        Args:
            since: ISO timestamp to fetch records modified after.

        Returns:
            List of CRM record dicts.
        """
        ...


class HubSpotAdapter(CRMAdapter):
    """HubSpot CRM adapter using HubSpot API v3."""

    def __init__(self, api_key: str, base_url: str = "https://api.hubapi.com"):
        self._api_key = api_key
        self._base_url = base_url

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def push_lead(self, lead_data: dict) -> dict:
        """Create or update a contact in HubSpot."""
        properties = {
            "email": lead_data.get("email", ""),
            "firstname": lead_data.get("first_name", ""),
            "lastname": lead_data.get("last_name", ""),
            "company": lead_data.get("company", ""),
            "jobtitle": lead_data.get("title", ""),
        }
        payload = {"properties": properties}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/crm/v3/objects/contacts",
                json=payload,
                headers=self._headers(),
            )
            if response.status_code in (200, 201):
                data = response.json()
                return {"id": data.get("id"), "status": "created"}
            return {"error": response.text, "status_code": response.status_code}

    async def update_deal_stage(self, deal_id: str, stage: str) -> dict:
        """Update a deal stage in HubSpot."""
        payload = {"properties": {"dealstage": stage}}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                f"{self._base_url}/crm/v3/objects/deals/{deal_id}",
                json=payload,
                headers=self._headers(),
            )
            if response.status_code == 200:
                data = response.json()
                return {"id": data.get("id"), "stage": stage, "status": "updated"}
            return {"error": response.text, "status_code": response.status_code}

    async def sync_from_crm(self, since: Optional[str] = None) -> list[dict]:
        """Pull recent contacts from HubSpot."""
        params: dict[str, Any] = {"limit": 100}
        if since:
            params["filterGroups"] = [
                {
                    "filters": [
                        {
                            "propertyName": "lastmodifieddate",
                            "operator": "GTE",
                            "value": since,
                        }
                    ]
                }
            ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/crm/v3/objects/contacts",
                params=params,
                headers=self._headers(),
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            return []


class PipedriveAdapter(CRMAdapter):
    """Pipedrive CRM adapter."""

    def __init__(self, api_token: str, base_url: str = "https://api.pipedrive.com/v1"):
        self._api_token = api_token
        self._base_url = base_url

    def _params(self) -> dict:
        return {"api_token": self._api_token}

    async def push_lead(self, lead_data: dict) -> dict:
        """Create a person and optionally a deal in Pipedrive."""
        person_payload = {
            "name": f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip(),
            "email": [lead_data.get("email", "")],
            "org_id": None,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create person
            response = await client.post(
                f"{self._base_url}/persons",
                json=person_payload,
                params=self._params(),
            )
            if response.status_code in (200, 201):
                data = response.json()
                person_id = data.get("data", {}).get("id")

                # Create deal linked to person
                deal_payload = {
                    "title": f"Deal - {lead_data.get('company', 'Unknown')}",
                    "person_id": person_id,
                }
                deal_resp = await client.post(
                    f"{self._base_url}/deals",
                    json=deal_payload,
                    params=self._params(),
                )
                deal_data = deal_resp.json() if deal_resp.status_code in (200, 201) else {}
                return {
                    "person_id": person_id,
                    "deal_id": deal_data.get("data", {}).get("id"),
                    "status": "created",
                }
            return {"error": response.text, "status_code": response.status_code}

    async def update_deal_stage(self, deal_id: str, stage: str) -> dict:
        """Update deal stage in Pipedrive."""
        payload = {"stage_id": stage}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{self._base_url}/deals/{deal_id}",
                json=payload,
                params=self._params(),
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "id": data.get("data", {}).get("id"),
                    "stage": stage,
                    "status": "updated",
                }
            return {"error": response.text, "status_code": response.status_code}

    async def sync_from_crm(self, since: Optional[str] = None) -> list[dict]:
        """Pull recent persons from Pipedrive."""
        params = self._params()
        if since:
            params["since_timestamp"] = since

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/recents",
                params={**params, "items": "person", "limit": 100},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", []) or []
            return []


class CRMSyncManager:
    """Routes CRM operations to the correct adapter based on tenant settings."""

    def __init__(self):
        self._adapters: dict[str, CRMAdapter] = {}

    def get_adapter(self, tenant_settings: dict) -> Optional[CRMAdapter]:
        """Get the appropriate CRM adapter based on tenant settings.

        Args:
            tenant_settings: Tenant settings dict with crm_provider, crm_api_key, etc.

        Returns:
            CRMAdapter instance or None if no CRM configured.
        """
        provider = tenant_settings.get("crm_provider")
        api_key = tenant_settings.get("crm_api_key", "")

        if not provider or not api_key:
            return None

        cache_key = f"{provider}:{api_key[:8]}"
        if cache_key not in self._adapters:
            if provider == "hubspot":
                self._adapters[cache_key] = HubSpotAdapter(api_key=api_key)
            elif provider == "pipedrive":
                self._adapters[cache_key] = PipedriveAdapter(api_token=api_key)
            else:
                logger.warning("Unknown CRM provider: %s", provider)
                return None

        return self._adapters[cache_key]

    async def push_lead(self, tenant_settings: dict, lead_data: dict) -> dict:
        """Push a lead to the tenant's configured CRM."""
        adapter = self.get_adapter(tenant_settings)
        if adapter is None:
            return {"status": "skipped", "reason": "no CRM configured"}
        return await adapter.push_lead(lead_data)

    async def update_deal_stage(
        self, tenant_settings: dict, deal_id: str, stage: str
    ) -> dict:
        """Update a deal stage in the tenant's configured CRM."""
        adapter = self.get_adapter(tenant_settings)
        if adapter is None:
            return {"status": "skipped", "reason": "no CRM configured"}
        return await adapter.update_deal_stage(deal_id, stage)

    async def sync_from_crm(
        self, tenant_settings: dict, since: Optional[str] = None
    ) -> list[dict]:
        """Pull recent records from the tenant's configured CRM."""
        adapter = self.get_adapter(tenant_settings)
        if adapter is None:
            return []
        return await adapter.sync_from_crm(since)
