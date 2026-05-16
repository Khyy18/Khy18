"""Audit logging middleware for FastAPI."""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Methods that trigger audit logging
AUDITED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that logs POST/PUT/DELETE operations to audit_log table."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method in AUDITED_METHODS and response.status_code < 400:
            try:
                await self._log_operation(request, response)
            except Exception as e:
                logger.warning(f"Audit log failed: {e}")

        return response

    async def _log_operation(self, request: Request, response: Response):
        """Create audit log entry for the request."""
        from backend.database import get_db

        path = request.url.path
        # Extract entity_type from path (e.g. /api/v1/employees -> employees)
        parts = [p for p in path.split("/") if p]
        entity_type = None
        entity_id = None
        if len(parts) >= 3:
            entity_type = parts[2] if len(parts) > 2 else None
        if len(parts) >= 4:
            entity_id = parts[3]

        ip_address = request.client.host if request.client else None

        entry = AuditLog(
            action=request.method,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
        )

        # Use the app's get_db dependency (respects test overrides)
        app = request.app
        if hasattr(app, "dependency_overrides") and get_db in app.dependency_overrides:
            db_gen = app.dependency_overrides[get_db]()
        else:
            db_gen = get_db()

        async for session in db_gen:
            session.add(entry)
            await session.commit()
            break
