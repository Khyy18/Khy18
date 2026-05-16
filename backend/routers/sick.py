"""Sick leave calculation endpoint."""

import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from backend.config import settings
from backend.schemas.calculators import SickCalculateRequest, SickCalculateResponse

router = APIRouter(prefix="/sick", tags=["calculators"])


def calculate_sick(earnings_2y: float, stazh_bracket: str, days: int) -> dict:
    """Calculate sick leave pay - same logic as bot's calculate_sick."""
    if stazh_bracket == "<5":
        percent = 0.60
    elif stazh_bracket == "5-8":
        percent = 0.80
    else:
        percent = 1.00

    daily = (earnings_2y / 730) * percent
    total_gross = daily * days
    ndfl = total_gross * settings.NDFL_RATE
    total_net = total_gross - ndfl

    return {
        "stazh_bracket": stazh_bracket,
        "percent": percent,
        "earnings_2y": earnings_2y,
        "daily": daily,
        "days": days,
        "total_gross": total_gross,
        "ndfl": ndfl,
        "total_net": total_net,
    }


@router.post("/calculate", response_model=SickCalculateResponse)
async def sick_calculate(data: SickCalculateRequest):
    result = calculate_sick(data.earnings_2y, data.stazh_bracket, data.days)
    return result


@router.post("/export-excel")
async def export_sick_excel(data: SickCalculateRequest):
    """Generate Excel sick leave report."""
    result = calculate_sick(data.earnings_2y, data.stazh_bracket, data.days)

    wb = Workbook()
    ws = wb.active
    ws.title = "\u0411\u043e\u043b\u044c\u043d\u0438\u0447\u043d\u044b\u0439"

    headers = [
        "\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440",
        "\u0417\u043d\u0430\u0447\u0435\u043d\u0438\u0435",
    ]
    ws.append(headers)
    ws.append(["\u0414\u043e\u0445\u043e\u0434 \u0437\u0430 2 \u0433\u043e\u0434\u0430", result["earnings_2y"]])
    ws.append(["\u0421\u0442\u0430\u0436", result["stazh_bracket"]])
    ws.append(["\u041f\u0440\u043e\u0446\u0435\u043d\u0442", f"{int(result['percent'] * 100)}%"])
    ws.append(["\u0421\u0440\u0435\u0434\u043d\u0435\u0434\u043d\u0435\u0432\u043d\u043e\u0439", result["daily"]])
    ws.append(["\u0414\u043d\u0435\u0439", result["days"]])
    ws.append(["\u041d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043e", result["total_gross"]])
    ws.append(["\u041d\u0414\u0424\u041b", result["ndfl"]])
    ws.append(["\u041a \u0432\u044b\u043f\u043b\u0430\u0442\u0435", result["total_net"]])

    ws.protection.sheet = True
    ws.protection.password = settings.EXCEL_PASSWORD

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sick_leave.xlsx"},
    )
