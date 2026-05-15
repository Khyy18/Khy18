"""Deliverability test endpoint for testing email placement via seed addresses.

Provides POST /api/email/test-deliverability to trigger deliverability testing
by sending test emails to specified seed addresses and returning results.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from channels.email.deliverability_test import DeliverabilityTester

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["deliverability"])


class TestDeliverabilityRequest(BaseModel):
    """Request body for the test-deliverability endpoint."""

    domain: str
    seed_addresses: list[str] = []


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
) -> TestDeliverabilityResponse:
    """Send test emails to seed addresses and return deliverability results.

    Instantiates a DeliverabilityTester and sends a test email to each
    seed address provided. Returns the results for each send attempt.
    """
    tester = DeliverabilityTester()
    results: list[dict] = []

    for address in payload.seed_addresses:
        result = await tester.send_test_email(payload.domain, address)
        results.append(result)

    logger.info(
        "Deliverability test completed: domain=%s, seeds=%d",
        payload.domain,
        len(payload.seed_addresses),
    )

    return TestDeliverabilityResponse(
        results=results,
        domain=payload.domain,
        test_count=len(results),
    )
