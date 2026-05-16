"""KBK (budget classification codes) search endpoints."""

from typing import List

from fastapi import APIRouter, Query

from backend.schemas.kbk import KBKEntry, KBKSearchResponse

# KBK data (same as bot's data/kbk_codes.py)
KBK_CODES = [
    {"code": "000 1 02 02010 06 1010 160", "short_name": "Страховые взносы ПФР", "description": "Страховые взносы на обязательное пенсионное страхование", "kvr": "119"},
    {"code": "000 1 02 02101 08 1013 160", "short_name": "Взносы ОМС", "description": "Страховые взносы на обязательное медицинское страхование", "kvr": "119"},
    {"code": "000 1 02 02090 07 1010 160", "short_name": "Взносы ФСС", "description": "Страховые взносы на обязательное социальное страхование", "kvr": "119"},
    {"code": "182 1 01 02010 01 1000 110", "short_name": "НДФЛ", "description": "Налог на доходы физических лиц с зарплаты", "kvr": "111"},
    {"code": "000 1 02 02050 07 1000 160", "short_name": "Взносы НС и ПЗ", "description": "Страховые взносы на травматизм (несчастные случаи)", "kvr": "119"},
    {"code": "000 1 01 02010 01 1000 110", "short_name": "Заработная плата", "description": "Оплата труда работников учреждения", "kvr": "111"},
    {"code": "000 1 01 02020 01 1000 110", "short_name": "Прочие выплаты", "description": "Иные выплаты персоналу (компенсации, пособия)", "kvr": "112"},
    {"code": "000 2 01 02000 02 0000 244", "short_name": "Продукты питания", "description": "Приобретение продуктов питания для воспитанников", "kvr": "244"},
    {"code": "000 2 01 02000 02 0000 223", "short_name": "Коммунальные услуги", "description": "Оплата коммунальных услуг (вода, тепло, электричество)", "kvr": "244"},
    {"code": "000 2 01 02000 02 0000 225", "short_name": "Содержание имущества", "description": "Работы и услуги по содержанию имущества (текущий ремонт)", "kvr": "244"},
]

POPULAR_KBK = KBK_CODES[:10]

router = APIRouter(prefix="/kbk", tags=["kbk"])


def search_kbk(query: str) -> List[dict]:
    """Search KBK codes by substring (case-insensitive)."""
    query_lower = query.lower()
    results = []
    for entry in KBK_CODES:
        if (
            query_lower in entry["code"].lower()
            or query_lower in entry["short_name"].lower()
            or query_lower in entry["description"].lower()
        ):
            results.append(entry)
    return results


@router.get("/search", response_model=KBKSearchResponse)
async def kbk_search(q: str = Query(..., min_length=1)):
    results = search_kbk(q)
    return KBKSearchResponse(
        results=[KBKEntry(**r) for r in results],
        count=len(results),
    )


@router.get("/popular", response_model=KBKSearchResponse)
async def kbk_popular():
    return KBKSearchResponse(
        results=[KBKEntry(**r) for r in POPULAR_KBK],
        count=len(POPULAR_KBK),
    )
