"""Vacation calculation endpoint."""

import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from backend.config import settings
from backend.schemas.calculators import VacationCalculateRequest, VacationCalculateResponse

router = APIRouter(prefix="/vacation", tags=["calculators"])


def calculate_vacation(total_12_months: float, days: int) -> dict:
    """Calculate vacation pay - same logic as bot's calculate_vacation."""
    avg_monthly = total_12_months / 12
    avg_daily = total_12_months / 12 / settings.AVG_DAYS_MONTH
    vacation_gross = avg_daily * days
    ndfl = vacation_gross * settings.NDFL_RATE
    vacation_net = vacation_gross - ndfl
    return {
        "total_12_months": total_12_months,
        "avg_monthly": avg_monthly,
        "avg_daily": avg_daily,
        "days": days,
        "vacation_gross": vacation_gross,
        "ndfl": ndfl,
        "vacation_net": vacation_net,
    }


@router.post("/calculate", response_model=VacationCalculateResponse)
async def vacation_calculate(data: VacationCalculateRequest):
    result = calculate_vacation(data.total_12_months, data.days)
    return result


@router.post("/export-excel")
async def export_vacation_excel(data: VacationCalculateRequest):
    """Generate Excel vacation pay report."""
    result = calculate_vacation(data.total_12_months, data.days)

    wb = Workbook()
    ws = wb.active
    ws.title = "\u041e\u0442\u043f\u0443\u0441\u043a\u043d\u044b\u0435"

    headers = [
        "\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440",
        "\u0417\u043d\u0430\u0447\u0435\u043d\u0438\u0435",
    ]
    ws.append(headers)
    ws.append(["\u0414\u043e\u0445\u043e\u0434 \u0437\u0430 12 \u043c\u0435\u0441.", result["total_12_months"]])
    ws.append(["\u0421\u0440\u0435\u0434\u043d\u0435\u043c\u0435\u0441\u044f\u0447\u043d\u044b\u0439", result["avg_monthly"]])
    ws.append(["\u0421\u0440\u0435\u0434\u043d\u0435\u0434\u043d\u0435\u0432\u043d\u043e\u0439", result["avg_daily"]])
    ws.append(["\u0414\u043d\u0435\u0439 \u043e\u0442\u043f\u0443\u0441\u043a\u0430", result["days"]])
    ws.append(["\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043e", result["vacation_gross"]])
    ws.append(["\u041d\u0414\u0424\u041b", result["ndfl"]])
    ws.append(["\u041a \u0432\u044b\u043f\u043b\u0430\u0442\u0435", result["vacation_net"]])

    ws.protection.sheet = True
    ws.protection.password = settings.EXCEL_PASSWORD

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=vacation.xlsx"},
    )
