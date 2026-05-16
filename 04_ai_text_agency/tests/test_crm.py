"""Тесты для CRM-модуля: models, service, auto_detect_stage."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def crm_db(tmp_path):
    """Фикстура: временная БД для CRM."""
    db_path = str(tmp_path / "test_crm.db")
    with patch("crm.models.DB_PATH", db_path):
        from crm import models
        models.init_db()
        yield db_path


def test_create_client(crm_db):
    """Создание клиента и получение по tg_id."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models

        client_id = models.create_client(123456, "Тест Пользователь")
        assert client_id is not None
        assert client_id > 0

        client = models.get_client(123456)
        assert client is not None
        assert client["tg_id"] == 123456
        assert client["name"] == "Тест Пользователь"
        assert client["stage"] == "lead"


def test_update_stage(crm_db):
    """Обновление этапа воронки."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models

        models.create_client(111, "Клиент А")

        success = models.update_stage(111, "trial")
        assert success is True

        client = models.get_client(111)
        assert client["stage"] == "trial"


def test_update_stage_invalid(crm_db):
    """Обновление на невалидный этап - отказ."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models

        models.create_client(222, "Клиент Б")

        success = models.update_stage(222, "invalid_stage")
        assert success is False


def test_list_clients_by_stage(crm_db):
    """Список клиентов по этапу."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models

        models.create_client(1001, "Лид 1")
        models.create_client(1002, "Лид 2")
        models.create_client(1003, "Платный")
        models.update_stage(1003, "paid")

        leads = models.list_clients_by_stage("lead")
        assert len(leads) == 2

        paid = models.list_clients_by_stage("paid")
        assert len(paid) == 1
        assert paid[0]["name"] == "Платный"


def test_funnel_stats(crm_db):
    """Статистика воронки - подсчет по этапам."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models

        models.create_client(2001, "А")
        models.create_client(2002, "Б")
        models.create_client(2003, "В")
        models.update_stage(2002, "trial")
        models.update_stage(2003, "paid")

        stats = models.get_funnel_stats()
        assert stats["lead"] == 1
        assert stats["trial"] == 1
        assert stats["paid"] == 1
        assert stats["churned"] == 0


def test_service_transition(crm_db):
    """CRMService.transition - валидный переход."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models
        from crm.service import CRMService

        models.create_client(3001, "Сервис Тест")
        service = CRMService()

        assert service.transition(3001, "trial") is True
        client = models.get_client(3001)
        assert client["stage"] == "trial"


def test_service_transition_invalid_back(crm_db):
    """CRMService.transition - нельзя перейти назад."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models
        from crm.service import CRMService

        models.create_client(3002, "Назад Тест")
        models.update_stage(3002, "paid")
        service = CRMService()

        # Нельзя из paid в trial
        assert service.transition(3002, "trial") is False
        client = models.get_client(3002)
        assert client["stage"] == "paid"


def test_service_transition_to_churned(crm_db):
    """CRMService.transition - churned разрешен из любого этапа."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models
        from crm.service import CRMService

        models.create_client(3003, "Чурн Тест")
        service = CRMService()

        assert service.transition(3003, "churned") is True
        client = models.get_client(3003)
        assert client["stage"] == "churned"


def test_auto_detect_stage(crm_db):
    """CRMService.auto_detect_stage - маппинг событий."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models
        from crm.service import CRMService

        models.create_client(4001, "Авто Тест")
        service = CRMService()

        # signup -> lead (уже lead, не изменится - одинаковый уровень)
        assert service.auto_detect_stage(4001, "trial_start") is True
        client = models.get_client(4001)
        assert client["stage"] == "trial"

        assert service.auto_detect_stage(4001, "first_payment") is True
        client = models.get_client(4001)
        assert client["stage"] == "paid"


def test_auto_detect_unknown_event(crm_db):
    """CRMService.auto_detect_stage - неизвестное событие."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models
        from crm.service import CRMService

        models.create_client(4002, "Неизвестный")
        service = CRMService()

        assert service.auto_detect_stage(4002, "unknown_event") is False


def test_get_funnel_via_service(crm_db):
    """CRMService.get_funnel - возвращает статистику."""
    with patch("crm.models.DB_PATH", crm_db):
        from crm import models
        from crm.service import CRMService

        models.create_client(5001, "Ф1")
        models.create_client(5002, "Ф2")
        service = CRMService()

        funnel = service.get_funnel()
        assert funnel["lead"] == 2
        assert funnel["trial"] == 0
