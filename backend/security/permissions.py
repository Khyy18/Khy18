"""Role-based access control (RBAC) for FastAPI endpoints."""

from enum import Enum
from typing import Tuple

from fastapi import Header, HTTPException, status


class Role(str, Enum):
    admin = "admin"
    cashier = "cashier"
    director = "director"


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: restrict access to specified roles.

    Usage:
        @router.delete("/...", dependencies=[Depends(require_role("admin"))])
    """

    async def _check_role(x_user_role: str = Header(default="")) -> str:
        """Verify the user's role from X-User-Role header."""
        role = x_user_role.lower().strip()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not specified",
            )
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not authorized. Required: {', '.join(allowed_roles)}",
            )
        return role

    return _check_role
