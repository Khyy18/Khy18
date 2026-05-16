"""Salary calculation endpoint."""

import io
from typing import List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from backend.config import settings
from backend.schemas.calculators import SalaryCalculateRequest, SalaryCalculateResponse
from backend.schemas.payroll import PayrollRequest, PayrollResponse, PayrollEmployeeResult

router = APIRouter(prefix="/salary", tags=["calculators"])


def calculate_salary(
    oklad: float, rate: float, stazh_percent: float, category_percent: float = 0
) -> dict:
    """Calculate salary breakdown - same logic as bot's calculate_salary."""
    nachisleno = oklad * rate * (1 + stazh_percent / 100 + category_percent / 100)
    ndfl = nachisleno * settings.NDFL_RATE
    pfr = nachisleno * settings.PFR_RATE
    oms = nachisleno * settings.OMS_RATE
    fss = nachisleno * settings.FSS_RATE
    fss_ns = nachisleno * settings.FSS_NS_RATE
    total_contributions = pfr + oms + fss + fss_ns
    na_ruki = nachisleno - ndfl
    return {
        "nachisleno": nachisleno,
        "ndfl": ndfl,
        "pfr": pfr,
        "oms": oms,
        "fss": fss,
        "fss_ns": fss_ns,
        "total_contributions": total_contributions,
        "na_ruki": na_ruki,
    }


@router.post("/calculate", response_model=SalaryCalculateResponse)
async def salary_calculate(data: SalaryCalculateRequest):
    result = calculate_salary(data.oklad, data.rate, data.stazh_percent, data.category_percent)
    return result


@router.post("/payroll", response_model=PayrollResponse)
async def payroll(data: PayrollRequest):
    """Calculate salary for multiple employees."""
    results: List[PayrollEmployeeResult] = []
    totals = {
        "nachisleno": 0.0,
        "ndfl": 0.0,
        "pfr": 0.0,
        "oms": 0.0,
        "fss": 0.0,
        "fss_ns": 0.0,
        "na_ruki": 0.0,
    }

    for emp in data.employees:
        calc = calculate_salary(emp.oklad, emp.rate, emp.stazh_percent, emp.category_percent)
        result = PayrollEmployeeResult(
            fio=emp.fio,
            oklad=emp.oklad,
            rate=emp.rate,
            nachisleno=calc["nachisleno"],
            ndfl=calc["ndfl"],
            pfr=calc["pfr"],
            oms=calc["oms"],
            fss=calc["fss"],
            fss_ns=calc["fss_ns"],
            na_ruki=calc["na_ruki"],
        )
        results.append(result)
        for key in totals:
            totals[key] += calc[key]

    return PayrollResponse(employees=results, totals=totals)


@router.post("/export-excel")
async def export_excel(data: PayrollRequest):
    """Generate Excel payroll report."""
    wb = Workbook()
    ws = wb.active
    ws.title = "\u0412\u0435\u0434\u043e\u043c\u043e\u0441\u0442\u044c"

    headers = [
        "\u0424\u0418\u041e", "\u041e\u043a\u043b\u0430\u0434", "\u0421\u0442\u0430\u0432\u043a\u0430",
        "\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043e", "\u041d\u0414\u0424\u041b",
        "\u041f\u0424\u0420", "\u041e\u041c\u0421", "\u0424\u0421\u0421",
        "\u0424\u0421\u0421 \u041d\u0421", "\u041d\u0430 \u0440\u0443\u043a\u0438",
    ]
    ws.append(headers)

    totals = {
        "oklad": 0.0,
        "rate": 0.0,
        "nachisleno": 0.0,
        "ndfl": 0.0,
        "pfr": 0.0,
        "oms": 0.0,
        "fss": 0.0,
        "fss_ns": 0.0,
        "na_ruki": 0.0,
    }

    for emp in data.employees:
        calc = calculate_salary(emp.oklad, emp.rate, emp.stazh_percent, emp.category_percent)
        row = [
            emp.fio,
            emp.oklad,
            emp.rate,
            calc["nachisleno"],
            calc["ndfl"],
            calc["pfr"],
            calc["oms"],
            calc["fss"],
            calc["fss_ns"],
            calc["na_ruki"],
        ]
        ws.append(row)
        totals["oklad"] += emp.oklad
        totals["rate"] += emp.rate
        totals["nachisleno"] += calc["nachisleno"]
        totals["ndfl"] += calc["ndfl"]
        totals["pfr"] += calc["pfr"]
        totals["oms"] += calc["oms"]
        totals["fss"] += calc["fss"]
        totals["fss_ns"] += calc["fss_ns"]
        totals["na_ruki"] += calc["na_ruki"]

    # Totals row
    ws.append([
        "\u0418\u0442\u043e\u0433\u043e",
        totals["oklad"],
        totals["rate"],
        totals["nachisleno"],
        totals["ndfl"],
        totals["pfr"],
        totals["oms"],
        totals["fss"],
        totals["fss_ns"],
        totals["na_ruki"],
    ])

    # Password-protect the sheet
    ws.protection.sheet = True
    ws.protection.password = settings.EXCEL_PASSWORD

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=payroll.xlsx"},
    )
