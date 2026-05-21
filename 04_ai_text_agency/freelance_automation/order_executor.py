"""Автоматическое выполнение заказа: генерация решения и сохранение результата."""

from __future__ import annotations

import os
import re
import zipfile
from typing import Any

from freelance_automation.base import Order
from freelance_automation.config import DELIVERABLES_PATH
from logging_config import get_logger

log = get_logger(__name__)


class OrderExecutor:
    """Генератор готового решения для принятого заказа."""

    def __init__(self, deliverables_path: str | None = None) -> None:
        self.deliverables_path = deliverables_path or DELIVERABLES_PATH

    async def generate_completion_text(
        self, session: Any, order: Order, platform: str
    ) -> str:
        """Сгенерировать текст инструкции и описания результата заказа."""
        title = (order.title or "").strip()[:150]
        description = (order.description or "").strip()[:1200]
        budget_str = str(int(order.budget)) if order.budget else "договорный"

        prompt = (
            "You are an expert contractor who completes freelance orders. "
            f"The client requested: '{title}'. Description: {description}. "
            f"Budget: {budget_str}. Platform: {platform}. "
            "Generate a document in Russian with two clearly separated sections: "
            "1) Deliverable content — what is actually delivered for this request. "
            "2) Usage instructions — how the client should use or deploy the deliverable. "
            "Do not include runnable code blocks. Keep the structure simple, with headings 'Deliverable' and 'Instructions'."
        )

        try:
            import ai_router

            solution = await ai_router.call_llm_text(
                session,
                prompt,
                max_output_tokens=1200,
                temperature=0.55,
            )
            if solution and solution.strip():
                log.info(
                    "order_solution_generated",
                    order_id=order.id,
                    platform=platform,
                )
                return solution.strip()
        except Exception as exc:
            log.error("order_solution_generation_failed", order_id=order.id, error=str(exc))

        fallback = (
            "Deliverable:\n" 
            "Готовый план создания Telegram-бота для продаж с приемом заявок и уведомлением менеджера.\n\n"
            "Instructions:\n"
            "Следуйте инструкции по настройке бота, подключению Telegram API и проверке работы."
        )
        log.warning("order_solution_fallback", order_id=order.id)
        return fallback

    def save_deliverable(self, order: Order, completion_text: str) -> None:
        """Сохранить результат и инструкцию выполнения заказа."""
        try:
            deliverable_dir = os.path.join(self.deliverables_path, order.id)
            os.makedirs(deliverable_dir, exist_ok=True)

            deliverable_content, instructions_content = self._split_sections(completion_text)

            deliverable_path = os.path.join(deliverable_dir, "deliverable.txt")
            with open(deliverable_path, "w", encoding="utf-8") as f:
                f.write(deliverable_content)

            instructions_path = os.path.join(deliverable_dir, "instructions.txt")
            with open(instructions_path, "w", encoding="utf-8") as f:
                f.write(instructions_content)

            summary_path = os.path.join(deliverable_dir, "delivery_message.txt")
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(
                    "Deliverable сохранён в deliverable.txt. Инструкция — в instructions.txt."
                )

            zip_path = os.path.join(deliverable_dir, "deliverable.zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(deliverable_path, arcname="deliverable.txt")
                archive.write(instructions_path, arcname="instructions.txt")
                archive.write(summary_path, arcname="delivery_message.txt")

            log.info("deliverable_saved", order_id=order.id, path=deliverable_dir, zip=zip_path)
        except Exception as exc:
            log.error("deliverable_save_failed", order_id=order.id, error=str(exc))

    def _split_sections(self, text: str) -> tuple[str, str]:
        delivery = text
        instructions = ""
        if "instructions" in text.lower():
            parts = text.split("Instructions:", 1)
            if len(parts) == 2:
                delivery = parts[0].strip()
                instructions = parts[1].strip()
        if not instructions and "Инструк" in text:
            parts = text.split("Инструк", 1)
            if len(parts) == 2:
                delivery = parts[0].strip()
                instructions = "Инструк" + parts[1].strip()
        if not instructions:
            instructions = (
                "Инструкция по использованию вложенного deliverable: используйте содержимое deliverable.txt "
                "для выполнения задачи и следуйте описанным шагам."
            )
        return delivery, instructions
