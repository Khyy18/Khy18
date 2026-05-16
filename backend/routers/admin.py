"""Admin endpoints for system management tasks."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.database import get_db
from backend.models.child import Child
from backend.models.employee import Employee
from backend.security.encryption import decrypt_value, encrypt_value, _current_version
from backend.security.permissions import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


def _already_latest_version(value: str) -> bool:
    """Check if an encrypted value already uses the latest key version."""
    if not value:
        return True
    prefix = f"v{_current_version()}:"
    return value.startswith(prefix)


@router.post(
    "/rotate-key",
    dependencies=[Depends(verify_bearer_token), Depends(require_role("admin"))],
)
async def rotate_encryption_key(db: AsyncSession = Depends(get_db)):
    """Re-encrypt all sensitive fields with the latest encryption key version.

    Decrypts each encrypted field using its current key version,
    then re-encrypts with the latest configured key version.
    Skips fields that are already encrypted with the latest version (idempotent).
    """
    count = 0

    # Re-encrypt Employee.fio
    result = await db.execute(select(Employee))
    employees = result.scalars().all()
    for emp in employees:
        if emp.fio and not _already_latest_version(emp.fio):
            decrypted = decrypt_value(emp.fio)
            emp.fio = encrypt_value(decrypted)
            count += 1

    # Re-encrypt Child.child_fio and Child.parent_fio
    result = await db.execute(select(Child))
    children = result.scalars().all()
    for child in children:
        if child.child_fio and not _already_latest_version(child.child_fio):
            decrypted = decrypt_value(child.child_fio)
            child.child_fio = encrypt_value(decrypted)
            count += 1
        if child.parent_fio and not _already_latest_version(child.parent_fio):
            decrypted = decrypt_value(child.parent_fio)
            child.parent_fio = encrypt_value(decrypted)
            count += 1

    await db.commit()

    return {"status": "ok", "re_encrypted_fields": count}
