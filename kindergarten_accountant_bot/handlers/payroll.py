"""Payroll export handler - generates Excel with salary for all employees."""
import io

from openpyxl import Workbook
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from kindergarten_accountant_bot.handlers.salary import calculate_salary
from kindergarten_accountant_bot.models.employee import get_employees
from kindergarten_accountant_bot.utils.formatting import _card, format_money
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button


async def payroll_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate payroll Excel for all employees and send as document."""
    query = update.callback_query
    await query.answer()

    employees = await get_employees()

    if not employees:
        await query.edit_message_text(
            "Нет сотрудников в базе. Сначала добавьте сотрудников.",
            reply_markup=back_to_menu_button(),
        )
        return

    # Calculate salary for each employee
    results = []
    for emp in employees:
        result = calculate_salary(
            oklad=emp.get("oklad", 30000),
            rate=emp.get("rate", 1.0),
            stazh_percent=emp.get("stazh_percent", 0),
            category_percent=emp.get("category_percent", 0),
        )
        result["fio"] = emp.get("fio", "Unknown")
        results.append(result)

    # Generate Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Ведомость"

    headers = ["ФИО", "Начислено", "НДФЛ", "ПФР", "ОМС", "ФСС", "ФСС НС", "На руки"]
    ws.append(headers)

    for r in results:
        ws.append([
            r["fio"],
            round(r["nachisleno"], 2),
            round(r["ndfl"], 2),
            round(r["pfr"], 2),
            round(r["oms"], 2),
            round(r["fss"], 2),
            round(r["fss_ns"], 2),
            round(r["na_ruki"], 2),
        ])

    # Totals row
    totals = ["ИТОГО"]
    for key in ["nachisleno", "ndfl", "pfr", "oms", "fss", "fss_ns", "na_ruki"]:
        totals.append(round(sum(r[key] for r in results), 2))
    ws.append(totals)

    # Save to bytes buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # Send summary card
    body_lines = [
        f"Сотрудников: {len(results)}",
        "\u2501" * 24,
    ]
    for r in results:
        body_lines.append(f"{r['fio']}: {format_money(r['na_ruki'])}")
    body_lines.append("\u2501" * 24)
    total_na_ruki = sum(r["na_ruki"] for r in results)
    body_lines.append(f"Итого на руки: {format_money(total_na_ruki)}")

    card = _card("Ведомость на всех", "\U0001f4ca", body_lines)
    await query.edit_message_text(card, parse_mode="HTML")

    # Send Excel file
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=buffer,
        filename="payroll.xlsx",
        caption="Расчётная ведомость",
        reply_markup=back_to_menu_button(),
    )


payroll_handler = CallbackQueryHandler(payroll_export, pattern="^menu_payroll$")
