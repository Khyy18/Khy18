"""Self-serve onboarding - guided campaign setup without human intervention."""

import json
import logging
from dataclasses import dataclass
from typing import Any

import aiosmtplib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Campaign,
    CampaignStatus,
    OnboardingStep,
    Sequence,
    Tenant,
    User,
)
from dashboard.auth import get_current_user
from dashboard.schemas import (
    OnboardingStatusResponse,
    OnboardingStep1Request,
    OnboardingStep2Request,
    OnboardingStep3Request,
    OnboardingStep4Request,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

logger = logging.getLogger(__name__)


async def _get_session():
    """Lazy wrapper around core.db.get_session to avoid import-time engine creation."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


class OnboardingSetupRequest(BaseModel):
    """Schema for the onboarding questionnaire data."""

    company_description: str
    ideal_customer_industry: str
    ideal_customer_company_size: str
    ideal_customer_titles: str
    problem_solved: str
    differentiator: str
    tone: str
    website_url: str = ""


@dataclass
class OnboardingService:
    """Encapsulates onboarding logic for testability."""

    session: AsyncSession
    llm_client: Any = None

    async def store_setup_data(
        self, tenant_id: Any, data: dict
    ) -> dict:
        """Store onboarding questionnaire answers in tenant settings."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
            )

        settings = dict(tenant.settings) if tenant.settings else {}
        settings["onboarding_data"] = data
        tenant.settings = settings
        await self.session.flush()
        return {"status": "ok", "step": "generate"}

    async def generate_campaign(self, tenant_id: Any) -> dict:
        """Use LLM to generate a campaign plan from onboarding data."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
            )

        settings = dict(tenant.settings) if tenant.settings else {}
        onboarding_data = settings.get("onboarding_data")
        if not onboarding_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No onboarding data found. Complete setup first.",
            )

        # Sanitize user inputs: strip instruction-like patterns to mitigate
        # prompt injection. User content is placed in a separate user message
        # role so it cannot override system instructions.
        def _sanitize(value: str) -> str:
            """Remove instruction-like patterns from user input."""
            import re
            # Strip patterns that look like prompt injection attempts
            value = re.sub(
                r"(?i)(ignore|forget|disregard)\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
                "",
                value,
            )
            value = re.sub(r"(?i)you\s+are\s+now\s+", "", value)
            value = re.sub(r"(?i)system\s*:", "", value)
            return value.strip()

        sanitized_data = {
            "company_description": _sanitize(onboarding_data.get("company_description", "")),
            "ideal_customer_industry": _sanitize(onboarding_data.get("ideal_customer_industry", "")),
            "ideal_customer_company_size": _sanitize(onboarding_data.get("ideal_customer_company_size", "")),
            "ideal_customer_titles": _sanitize(onboarding_data.get("ideal_customer_titles", "")),
            "problem_solved": _sanitize(onboarding_data.get("problem_solved", "")),
            "differentiator": _sanitize(onboarding_data.get("differentiator", "")),
            "tone": _sanitize(onboarding_data.get("tone", "professional")),
            "website_url": _sanitize(onboarding_data.get("website_url", "")),
        }

        # Use system/user role separation to isolate instructions from user content
        system_message = (
            "You are an expert outbound sales strategist. Based on the company info "
            "provided in the user message, generate a complete outbound campaign plan.\n\n"
            "Return a JSON object with:\n"
            "- campaign_name: string\n"
            "- value_proposition: string\n"
            "- icp_filter: object with industry, company_size, titles fields\n"
            "- sequence: array of 3 objects, each with step_type (initial, follow_up_1, follow_up_2), "
            "subject, and body fields\n\n"
            "Return ONLY valid JSON, no markdown."
        )

        user_message = (
            f"Company: {sanitized_data['company_description']}\n"
            f"Ideal Customer Industry: {sanitized_data['ideal_customer_industry']}\n"
            f"Ideal Customer Company Size: {sanitized_data['ideal_customer_company_size']}\n"
            f"Target Titles: {sanitized_data['ideal_customer_titles']}\n"
            f"Problem Solved: {sanitized_data['problem_solved']}\n"
            f"Differentiator: {sanitized_data['differentiator']}\n"
            f"Tone: {sanitized_data['tone']}\n"
            f"Website: {sanitized_data['website_url']}"
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        llm_response = await self.llm_client.generate(messages)

        # Parse LLM response
        try:
            if isinstance(llm_response, str):
                plan = json.loads(llm_response)
            else:
                plan = llm_response
        except (json.JSONDecodeError, TypeError):
            # Fallback plan if LLM returns non-JSON
            plan = {
                "campaign_name": f"Outbound - {onboarding_data.get('ideal_customer_industry', 'General')}",
                "value_proposition": onboarding_data.get("differentiator", ""),
                "icp_filter": {
                    "industry": onboarding_data.get("ideal_customer_industry", ""),
                    "company_size": onboarding_data.get("ideal_customer_company_size", ""),
                    "titles": onboarding_data.get("ideal_customer_titles", ""),
                },
                "sequence": [
                    {"step_type": "initial", "subject": "Quick question", "body": "Hi there..."},
                    {"step_type": "follow_up_1", "subject": "Following up", "body": "Just checking in..."},
                    {"step_type": "follow_up_2", "subject": "Last try", "body": "One more note..."},
                ],
            }

        # Create Sequence in DB
        steps = []
        sequence_data = plan.get("sequence", [])
        for i, step in enumerate(sequence_data):
            steps.append({
                "step_type": step.get("step_type", f"step_{i}"),
                "delay_days": i * 3,
                "subject": step.get("subject", ""),
                "body": step.get("body", ""),
            })

        sequence = Sequence(
            tenant_id=tenant_id,
            name=f"{plan.get('campaign_name', 'Onboarding')} Sequence",
            steps=steps,
        )
        self.session.add(sequence)
        await self.session.flush()
        await self.session.refresh(sequence)

        # Create Campaign in DB
        campaign = Campaign(
            tenant_id=tenant_id,
            name=plan.get("campaign_name", "Onboarding Campaign"),
            icp_filter=plan.get("icp_filter", {}),
            sequence_id=sequence.id,
            status=CampaignStatus.draft,
        )
        self.session.add(campaign)
        await self.session.flush()
        await self.session.refresh(campaign)

        # Store preview in tenant settings
        preview = {
            "campaign_name": plan.get("campaign_name", ""),
            "value_proposition": plan.get("value_proposition", ""),
            "icp_filter": plan.get("icp_filter", {}),
            "sequence": sequence_data,
            "campaign_id": str(campaign.id),
            "sequence_id": str(sequence.id),
        }
        settings["onboarding_preview"] = preview
        tenant.settings = settings
        await self.session.flush()

        return preview

    async def confirm_campaign(self, tenant_id: Any) -> dict:
        """Activate the most recent draft campaign for the tenant."""
        result = await self.session.execute(
            select(Campaign)
            .where(
                Campaign.tenant_id == tenant_id,
                Campaign.status == CampaignStatus.draft,
            )
            .order_by(Campaign.created_at.desc())
            .limit(1)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No draft campaign found to activate.",
            )

        campaign.status = CampaignStatus.active
        await self.session.flush()
        await self.session.refresh(campaign)

        return {
            "status": "activated",
            "campaign_id": str(campaign.id),
            "message": "Campaign activated! You'll see first replies in 3-5 days.",
        }


@router.post("/setup")
async def onboarding_setup(
    data: OnboardingSetupRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Store onboarding questionnaire answers."""
    service = OnboardingService(session=session)
    return await service.store_setup_data(
        tenant_id=current_user.tenant_id,
        data=data.model_dump(),
    )


@router.post("/generate")
async def onboarding_generate(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Generate campaign plan using LLM from stored onboarding data."""
    llm_client = request.app.state.llm_client
    service = OnboardingService(session=session, llm_client=llm_client)
    return await service.generate_campaign(tenant_id=current_user.tenant_id)


@router.post("/confirm")
async def onboarding_confirm(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Activate the generated draft campaign."""
    service = OnboardingService(session=session)
    return await service.confirm_campaign(tenant_id=current_user.tenant_id)


# ---------- Step-based Onboarding Flow ----------

# Ordered list of steps for progression tracking
_STEP_ORDER = [
    OnboardingStep.tenant_created,
    OnboardingStep.smtp_connected,
    OnboardingStep.icp_uploaded,
    OnboardingStep.campaign_activated,
    OnboardingStep.completed,
]


def _steps_completed(current_step: OnboardingStep) -> list[str]:
    """Return list of step values that have been completed (all before current)."""
    idx = _STEP_ORDER.index(current_step)
    return [s.value for s in _STEP_ORDER[:idx]]


@router.get("/status")
async def onboarding_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> OnboardingStatusResponse:
    """Return current onboarding step for the tenant."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    current = tenant.onboarding_step or OnboardingStep.tenant_created
    return OnboardingStatusResponse(
        current_step=current.value,
        steps_completed=_steps_completed(current),
        tenant_id=str(tenant.id),
    )


@router.post("/step1")
async def onboarding_step1(
    data: OnboardingStep1Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Step 1: Validate and store tenant info (company_name, domain)."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    current = tenant.onboarding_step or OnboardingStep.tenant_created
    if current != OnboardingStep.tenant_created:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step 1 already completed. Current step: " + current.value,
        )

    tenant.name = data.company_name
    tenant.domain = data.domain
    tenant.onboarding_step = OnboardingStep.smtp_connected
    await session.flush()

    return {"status": "ok", "next_step": "smtp_connected"}


@router.post("/step2")
async def onboarding_step2(
    data: OnboardingStep2Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Step 2: Test SMTP connection and store config."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    current = tenant.onboarding_step or OnboardingStep.tenant_created
    if current != OnboardingStep.smtp_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete previous steps first. Current step: " + current.value,
        )

    # Test SMTP connection
    try:
        smtp = aiosmtplib.SMTP(
            hostname=data.smtp_host, port=data.smtp_port, timeout=10
        )
        await smtp.connect()
        await smtp.quit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SMTP connection failed: {str(exc)}",
        )

    # Store SMTP config in tenant settings
    settings = dict(tenant.settings) if tenant.settings else {}
    settings["smtp"] = {
        "host": data.smtp_host,
        "port": data.smtp_port,
        "user": data.smtp_user,
        "password": data.smtp_password,
    }
    tenant.settings = settings
    tenant.onboarding_step = OnboardingStep.icp_uploaded
    await session.flush()

    return {"status": "ok", "next_step": "icp_uploaded"}


@router.post("/step3")
async def onboarding_step3(
    data: OnboardingStep3Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Step 3: Store ICP data."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    current = tenant.onboarding_step or OnboardingStep.tenant_created
    if current != OnboardingStep.icp_uploaded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete previous steps first. Current step: " + current.value,
        )

    # Store ICP data in tenant settings
    settings = dict(tenant.settings) if tenant.settings else {}
    settings["icp"] = {
        "industry": data.industry,
        "company_size": data.company_size,
        "titles": data.titles,
        "geo": data.geo,
    }
    tenant.settings = settings
    tenant.onboarding_step = OnboardingStep.campaign_activated
    await session.flush()

    return {"status": "ok", "next_step": "campaign_activated"}


@router.post("/step4")
async def onboarding_step4(
    data: OnboardingStep4Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Step 4: Create and activate a campaign from ICP data."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    current = tenant.onboarding_step or OnboardingStep.tenant_created
    if current != OnboardingStep.campaign_activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete previous steps first. Current step: " + current.value,
        )

    # Get ICP data from settings
    settings = dict(tenant.settings) if tenant.settings else {}
    icp_data = settings.get("icp", {})

    # Create sequence
    sequence = Sequence(
        tenant_id=tenant.id,
        name=f"{data.campaign_name} Sequence",
        steps=[
            {"step_type": "initial", "delay_days": 0, "subject": "Introduction", "body": "Hello"},
            {"step_type": "follow_up_1", "delay_days": 3, "subject": "Following up", "body": "Checking in"},
            {"step_type": "follow_up_2", "delay_days": 6, "subject": "Last note", "body": "One more thought"},
        ],
    )
    session.add(sequence)
    await session.flush()
    await session.refresh(sequence)

    # Create campaign from ICP data
    campaign = Campaign(
        tenant_id=tenant.id,
        name=data.campaign_name,
        icp_filter=icp_data,
        sequence_id=sequence.id,
        status=CampaignStatus.active,
    )
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)

    tenant.onboarding_step = OnboardingStep.completed
    await session.flush()

    return {
        "status": "ok",
        "campaign_id": str(campaign.id),
        "message": "Campaign activated! Onboarding complete.",
    }
