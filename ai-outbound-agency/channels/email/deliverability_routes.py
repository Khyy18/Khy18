"""Deliverability test endpoint for testing email placement via seed addresses.

Provides POST /api/email/test-deliverability to trigger deliverability testing
by sending test emails to specified seed addresses and returning results.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from channels.email.deliverability_test import DeliverabilityTester
from core.models import User
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["deliverability"])

# Simple email regex for validation
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Maximum seed addresses per request
MAX_SEED_ADDRESSES = 10


class TestDeliverabilityRequest(BaseModel):
    """Request body for the test-deliverability endpoint."""

    domain: str
    seed_addresses: list[str] = []

    @field_validator("seed_addresses")
    @classmethod
    def validate_seed_addresses(cls, v: list[str]) -> list[str]:
        """Validate seed addresses: max 10 items, valid email format."""
        if len(v) > MAX_SEED_ADDRESSES:
            raise ValueError(
                f"Maximum {MAX_SEED_ADDRESSES} seed addresses allowed per request"
            )
        for addr in v:
            if not _EMAIL_RE.match(addr):
                raise ValueError(f"Invalid email format: {addr}")
        return v


class TestDeliverabilityResponse(BaseModel):
    """Response body for the test-deliverability endpoint."""

    results: list[dict]
    domain: str
    test_count: int


@router.post(
    "/test-deliverability",
    response_model=TestDeliverabilityResponse,
)
async def run_deliverability_test(
    payload: TestDeliverabilityRequest,
    current_user: User = Depends(get_current_user),
) -> TestDeliverabilityResponse:
    """Send test emails to seed addresses and return deliverability results.

    Requires authentication. Validates seed addresses for format and count.
    Instantiates a DeliverabilityTester and sends a test email to each
    seed address provided. Returns the results for each send attempt.
    """
    tester = DeliverabilityTester()
    results: list[dict] = []

    for address in payload.seed_addresses:
        result = await tester.send_test_email(payload.domain, address)
        results.append(result)

    logger.info(
        "Deliverability test completed: domain=%s, seeds=%d, user=%s",
        payload.domain,
        len(payload.seed_addresses),
        current_user.email,
    )

    return TestDeliverabilityResponse(
        results=results,
        domain=payload.domain,
        test_count=len(results),
    )
