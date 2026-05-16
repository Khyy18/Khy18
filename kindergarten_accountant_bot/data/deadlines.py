"""Pre-configured recurring accounting deadlines for kindergarten."""

DEADLINES = [
    {
        "name": "6-НДФЛ",
        "description": "Расчёт сумм налога на доходы физических лиц",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [4, 7, 10, 1],
    },
    {
        "name": "РСВ",
        "description": "Расчёт по страховым взносам",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [1, 4, 7, 10],
    },
    {
        "name": "СЗВ-М (ЕФС-1)",
        "description": "Сведения о застрахованных лицах",
        "recurrence": "monthly",
        "day_of_month": 15,
        "months": list(range(1, 13)),
    },
    {
        "name": "Зарплата (аванс)",
        "description": "Выплата аванса сотрудникам",
        "recurrence": "monthly",
        "day_of_month": 25,
        "months": list(range(1, 13)),
    },
    {
        "name": "Зарплата (расчёт)",
        "description": "Выплата заработной платы",
        "recurrence": "monthly",
        "day_of_month": 10,
        "months": list(range(1, 13)),
    },
    {
        "name": "НДФЛ (перечисление)",
        "description": "Перечисление НДФЛ в бюджет",
        "recurrence": "monthly",
        "day_of_month": 28,
        "months": list(range(1, 13)),
    },
    {
        "name": "Страховые взносы",
        "description": "Перечисление страховых взносов (ПФР, ОМС, ФСС)",
        "recurrence": "monthly",
        "day_of_month": 28,
        "months": list(range(1, 13)),
    },
    {
        "name": "Налог на имущество",
        "description": "Авансовый платёж по налогу на имущество",
        "recurrence": "quarterly",
        "day_of_month": 28,
        "months": [4, 7, 10, 3],
    },
    {
        "name": "4-ФСС",
        "description": "Расчёт по взносам на травматизм",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [1, 4, 7, 10],
    },
    {
        "name": "Родительская плата",
        "description": "Сбор родительской платы за содержание ребёнка",
        "recurrence": "monthly",
        "day_of_month": 20,
        "months": list(range(1, 13)),
    },
]
