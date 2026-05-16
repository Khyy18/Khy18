"""Генерация PDF договора-оферты."""

import os
from datetime import datetime, timezone

from fpdf import FPDF

from .models import create_offer_record, get_offer
from .template import OFFER_TEMPLATE


# Путь к шрифту DejaVuSans для поддержки кириллицы
_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf")


class OfferGenerator:
    """Генератор PDF-оферт."""

    def generate_pdf(self, user_tg_id: int, user_name: str,
                     amount: float, service_description: str) -> tuple[bytes, int]:
        """Генерирует PDF оферту. Возвращает (pdf_bytes, offer_id)."""
        # Создаем запись в БД для получения offer_number
        offer_id = create_offer_record(user_tg_id, user_name, amount, service_description)
        offer = get_offer(offer_id)
        offer_number = offer["offer_number"]

        date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")

        # Заполняем шаблон
        text = OFFER_TEMPLATE.format(
            offer_number=offer_number,
            date=date_str,
            user_name=user_name,
            amount=f"{amount:.2f}",
            service_description=service_description,
        )

        # Создаем PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Пробуем загрузить DejaVuSans для кириллицы
        if os.path.exists(_FONT_PATH):
            pdf.add_font("DejaVu", "", _FONT_PATH)
            pdf.set_font("DejaVu", size=10)
        else:
            # Fallback: Helvetica (без кириллицы, но PDF валидный)
            pdf.set_font("Helvetica", size=10)

        # Записываем весь текст одним блоком
        pdf.multi_cell(0, 5, text.strip())

        pdf_bytes = pdf.output()
        return bytes(pdf_bytes), offer_id
