"""CRM-сервис: управление переходами клиентов по воронке."""

from __future__ import annotations

from crm import models
from logging_config import get_logger

log = get_logger(__name__)

# Допустимые переходы: из какого этапа в какой можно перейти.
STAGE_ORDER = {"lead": 0, "trial": 1, "paid": 2, "churned": 3}

# Маппинг событий на целевые этапы.
EVENT_STAGE_MAP = {
    "signup": "lead",
    "trial_start": "trial",
    "first_payment": "paid",
    "inactive_30d": "churned",
}


class CRMService:
    """Управление жизненным циклом клиентов."""

    def __init__(self) -> None:
        models.init_db()

    def transition(self, tg_id: int, new_stage: str) -> bool:
        """Перевести клиента на новый этап воронки.

        Валидирует порядок этапов (нельзя перейти назад, кроме churned).
        Возвращает True при успешном переходе.
        """
        if new_stage not in models.VALID_STAGES:
            log.warning("invalid_stage", tg_id=tg_id, stage=new_stage)
            return False

        client = models.get_client(tg_id)
        if client is None:
            log.warning("client_not_found", tg_id=tg_id)
            return False

        current_stage = client["stage"]

        # Churned можно из любого этапа
        if new_stage != "churned":
            if STAGE_ORDER.get(new_stage, 0) <= STAGE_ORDER.get(current_stage, 0):
                log.warning(
                    "invalid_transition",
                    tg_id=tg_id,
                    current=current_stage,
                    target=new_stage,
                )
                return False

        success = models.update_stage(tg_id, new_stage)
        if success:
            log.info(
                "stage_transition",
                tg_id=tg_id,
                old_stage=current_stage,
                new_stage=new_stage,
            )
        return success

    def auto_detect_stage(self, tg_id: int, event_type: str) -> bool:
        """Определить целевой этап по типу события и выполнить переход.

        Поддерживаемые события: signup, trial_start, first_payment, inactive_30d.
        """
        target_stage = EVENT_STAGE_MAP.get(event_type)
        if target_stage is None:
            log.warning("unknown_event_type", tg_id=tg_id, event_type=event_type)
            return False
        return self.transition(tg_id, target_stage)

    def get_funnel(self) -> dict[str, int]:
        """Получить статистику воронки."""
        return models.get_funnel_stats()
