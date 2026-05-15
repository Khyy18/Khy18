"""Dashboard HTML page views served via Jinja2 templates.

Design note: These view routes intentionally do NOT require server-side authentication.
Templates are HTML shells that contain no sensitive data. All data is fetched from
protected API endpoints (/api/*) which enforce JWT auth. The client-side app.js handles
auth gating by redirecting unauthenticated users to /login. This pattern keeps the
views layer simple and stateless while the API layer enforces the security boundary.
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["views"])

_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Render the registration page."""
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Render the dashboard overview page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_list_page(request: Request):
    """Render the campaigns list page."""
    return templates.TemplateResponse("campaigns/list.html", {"request": request})


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail_page(request: Request, campaign_id: str):
    """Render the campaign detail page."""
    return templates.TemplateResponse(
        "campaigns/detail.html",
        {"request": request, "campaign_id": campaign_id},
    )


@router.get("/leads", response_class=HTMLResponse)
async def leads_list_page(request: Request):
    """Render the leads list page."""
    return templates.TemplateResponse("leads/list.html", {"request": request})


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail_page(request: Request, lead_id: str):
    """Render the lead detail page."""
    return templates.TemplateResponse(
        "leads/detail.html",
        {"request": request, "lead_id": lead_id},
    )


@router.get("/sequences", response_class=HTMLResponse)
async def sequences_list_page(request: Request):
    """Render the sequences list page."""
    return templates.TemplateResponse("sequences/list.html", {"request": request})


@router.get("/sequences/{sequence_id}", response_class=HTMLResponse)
async def sequence_builder_page(request: Request, sequence_id: str):
    """Render the sequence builder page."""
    return templates.TemplateResponse(
        "sequences/builder.html",
        {"request": request, "sequence_id": sequence_id},
    )


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Render the analytics page."""
    return templates.TemplateResponse("analytics.html", {"request": request})


@router.get("/optimizer", response_class=HTMLResponse)
async def optimizer_page(request: Request):
    """Render the optimizer page."""
    return templates.TemplateResponse("optimizer.html", {"request": request})


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    """Render the billing page."""
    return templates.TemplateResponse("billing.html", {"request": request})


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    """Render the onboarding questionnaire page."""
    return templates.TemplateResponse("onboarding/step1.html", {"request": request})


@router.get("/onboarding/preview", response_class=HTMLResponse)
async def onboarding_preview_page(request: Request):
    """Render the onboarding preview page."""
    return templates.TemplateResponse("onboarding/step2.html", {"request": request})


@router.get("/onboarding/complete", response_class=HTMLResponse)
async def onboarding_complete_page(request: Request):
    """Render the onboarding completion page."""
    return templates.TemplateResponse("onboarding/step3.html", {"request": request})
