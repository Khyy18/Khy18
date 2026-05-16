"""Children CRUD endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.database import get_db
from backend.models.child import Child
from backend.schemas.child import ChildCreate, ChildResponse
from backend.security.encryption import encrypt_value, decrypt_value

router = APIRouter(prefix="/children", tags=["children"])


@router.get("", response_model=List[ChildResponse])
async def list_children(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Child))
    children = result.scalars().all()
    # Decrypt fio fields on read
    for child in children:
        child.child_fio = decrypt_value(child.child_fio)
        child.parent_fio = decrypt_value(child.parent_fio)
    return children


@router.post("", response_model=ChildResponse, status_code=201)
async def create_child(
    data: ChildCreate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    child = Child(
        child_fio=encrypt_value(data.child_fio),
        group_name=data.group_name,
        parent_fio=encrypt_value(data.parent_fio),
        discount_percent=data.discount_percent,
    )
    db.add(child)
    await db.commit()
    await db.refresh(child)
    # Decrypt for response
    child.child_fio = decrypt_value(child.child_fio)
    child.parent_fio = decrypt_value(child.parent_fio)
    return child


@router.delete("/{child_id}", status_code=204)
async def delete_child(
    child_id: int,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    result = await db.execute(select(Child).where(Child.id == child_id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    await db.delete(child)
    await db.commit()
