"""Инструменты финансов - бюджеты, счета, анализ затрат."""

from datetime import datetime

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Oscar."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Oscar")
        )
        agent = result.scalar_one_or_none()
        if agent:
            log = ActivityLog(
                agent_id=agent.id,
                action_type=action_type,
                action_description=description,
            )
            session.add(log)
            await session.commit()


@tool
async def calculate_budget(items: str) -> str:
    """Рассчитать бюджет по списку статей расходов.

    Args:
        items: Статьи расходов через запятую в формате "Название:Сумма" (например: "Хостинг:5000,Дизайн:15000,Разработка:50000")

    Returns:
        Детальная разбивка бюджета с итогом
    """
    entries = []
    errors = []

    for item in items.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            errors.append(f"  - Неверный формат: '{item}' (ожидается 'Название:Сумма')")
            continue
        parts = item.rsplit(":", 1)
        name = parts[0].strip()
        try:
            amount = float(parts[1].strip())
            entries.append((name, amount))
        except ValueError:
            errors.append(f"  - Неверная сумма: '{item}'")

    if not entries and errors:
        return "Ошибка парсинга бюджета:\n" + "\n".join(errors)

    if not entries:
        return "Ошибка: не указаны статьи расходов. Формат: 'Название:Сумма,Название:Сумма'"

    total = sum(amount for _, amount in entries)

    lines = ["Бюджет:", ""]
    lines.append(f"{'Статья':<25} {'Сумма':>12} {'Доля':>8}")
    lines.append("-" * 47)
    for name, amount in entries:
        share = (amount / total * 100) if total > 0 else 0
        lines.append(f"  {name:<23} {amount:>10.0f} {share:>6.1f}%")
    lines.append("-" * 47)
    lines.append(f"  {'ИТОГО':<23} {total:>10.0f} {'100.0%':>7}")

    if errors:
        lines.append("")
        lines.append("Предупреждения:")
        lines.extend(errors)

    result = "\n".join(lines)
    await _log_activity("budget_calculated", f"Бюджет рассчитан: {len(entries)} статей, итого {total:.0f}")
    return result


@tool
async def generate_invoice(client: str, items: str, currency: str = "RUB") -> str:
    """Сгенерировать счёт для клиента.

    Args:
        client: Название клиента/компании
        items: Позиции счёта через запятую в формате "Услуга:Сумма"
        currency: Валюта (RUB, USD, EUR)

    Returns:
        Форматированный счёт
    """
    entries = []
    for item in items.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        parts = item.rsplit(":", 1)
        name = parts[0].strip()
        try:
            amount = float(parts[1].strip())
            entries.append((name, amount))
        except ValueError:
            continue

    if not entries:
        return "Ошибка: не удалось распознать позиции счёта. Формат: 'Услуга:Сумма,Услуга:Сумма'"

    total = sum(amount for _, amount in entries)
    now = datetime.now()
    invoice_num = f"INV-{now.strftime('%Y%m%d')}-001"

    currency_symbols = {"RUB": "руб.", "USD": "$", "EUR": "EUR"}
    curr_symbol = currency_symbols.get(currency.upper(), currency)

    lines = [
        "=" * 50,
        f"СЧЁТ № {invoice_num}",
        f"Дата: {now.strftime('%d.%m.%Y')}",
        "=" * 50,
        "",
        f"Клиент: {client}",
        "",
        "Позиции:",
        f"{'№':<4} {'Описание':<25} {'Сумма':>12}",
        "-" * 43,
    ]

    for i, (name, amount) in enumerate(entries, 1):
        lines.append(f"{i:<4} {name:<25} {amount:>10.0f} {curr_symbol}")

    lines.append("-" * 43)
    lines.append(f"{'':4} {'ИТОГО:':<25} {total:>10.0f} {curr_symbol}")
    lines.append("")
    lines.append("Реквизиты для оплаты:")
    lines.append("  [Заполните реквизиты получателя]")
    lines.append("")
    lines.append(f"Срок оплаты: до {now.strftime('%d.%m.%Y')} + 14 дней")
    lines.append("=" * 50)

    result = "\n".join(lines)
    await _log_activity("invoice_generated", f"Счёт для {client}: {total:.0f} {curr_symbol}")
    return result


@tool
async def cost_analysis(period: str) -> str:
    """Провести анализ затрат за период.

    Args:
        period: Период анализа (месяц, квартал, год)

    Returns:
        Шаблон анализа затрат с категориями и рекомендациями
    """
    period_lower = period.lower()

    lines = [
        f"Анализ затрат за период: {period}",
        "",
        "Категории расходов:",
        "",
        "1. Постоянные расходы (Fixed Costs):",
        "   - Аренда/хостинг: [заполнить]",
        "   - Зарплаты: [заполнить]",
        "   - Подписки и лицензии: [заполнить]",
        "   - Страховка: [заполнить]",
        "",
        "2. Переменные расходы (Variable Costs):",
        "   - Маркетинг и реклама: [заполнить]",
        "   - Сервера (по нагрузке): [заполнить]",
        "   - Фрилансеры/подрядчики: [заполнить]",
        "   - Командировки: [заполнить]",
        "",
        "3. Единовременные расходы (One-time):",
        "   - Оборудование: [заполнить]",
        "   - Обучение: [заполнить]",
        "   - Лицензии (разовые): [заполнить]",
        "",
        "Рекомендации по оптимизации:",
        "  1. Пересмотрите подписки - отмените неиспользуемые сервисы",
        "  2. Рассмотрите годовые тарифы вместо месячных (экономия 15-20%)",
        "  3. Автоматизируйте рутинные процессы для снижения трудозатрат",
        "  4. Проведите аудит облачных ресурсов (правый размер инстансов)",
        "  5. Сравните поставщиков - возможна экономия на объёме",
        "",
        "Метрики для отслеживания:",
        f"  - Burn rate ({period}): общие расходы / количество дней",
        "  - Unit economics: стоимость привлечения клиента (CAC)",
        "  - ROI по каждой категории расходов",
        "  - Отношение постоянных к переменным расходам",
    ]

    result = "\n".join(lines)
    await _log_activity("cost_analysis", f"Анализ затрат за {period}")
    return result
