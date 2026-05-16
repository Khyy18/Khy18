"""Employee CRUD endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.database import get_db
from backend.models.employee import Employee
from backend.schemas.employee import EmployeeCreate, EmployeeResponse
from backend.security.encryption import encrypt_value, decrypt_value

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=List[EmployeeResponse])
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee))
    employees = result.scalars().all()
    # Decrypt fio on read
    for emp in employees:
        emp.fio = decrypt_value(emp.fio)
    return employees


@router.post("", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    employee = Employee(fio=encrypt_value(data.fio), position=data.position, rate=data.rate)
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    # Decrypt for response
    employee.fio = decrypt_value(employee.fio)
    return employee


@router.delete("/{employee_id}", status_code=204)
async def delete_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.delete(employee)
    await db.commit()
