"""Employee CRUD endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.employee import Employee
from backend.schemas.employee import EmployeeCreate, EmployeeResponse

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=List[EmployeeResponse])
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee))
    return result.scalars().all()


@router.post("", response_model=EmployeeResponse, status_code=201)
async def create_employee(data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    employee = Employee(fio=data.fio, position=data.position, rate=data.rate)
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


@router.delete("/{employee_id}", status_code=204)
async def delete_employee(employee_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.delete(employee)
    await db.commit()
