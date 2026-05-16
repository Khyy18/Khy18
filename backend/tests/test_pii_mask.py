"""Tests for PII masking utilities."""


from backend.middleware.pii_mask import (
    mask_fio,
    mask_inn,
    mask_phone,
    mask_all,
    pii_processor,
)


class TestMaskFio:
    """Tests for FIO masking."""

    def test_full_fio_three_words(self):
        result = mask_fio("Иванова Анна Петровна")
        assert result == "И***ва А.П."

    def test_two_word_name(self):
        result = mask_fio("Петров Иван")
        assert result == "П***ов И."

    def test_fio_embedded_in_sentence(self):
        result = mask_fio("ФИО: Иванова Анна Петровна получила зарплату")
        assert "И***ва А.П." in result
        assert "Иванова" not in result

    def test_multiple_fio_in_text(self):
        text = "Иванова Анна Петровна и Петров Иван пришли"
        result = mask_fio(text)
        assert "И***ва А.П." in result
        assert "П***ов И." in result

    def test_short_surname(self):
        result = mask_fio("Ли Вэй")
        # Short surname (2 chars) - first char + ***
        assert result == "Л*** В."

    def test_no_fio_not_modified(self):
        text = "Обычный текст без имен"
        result = mask_fio(text)
        assert result == text


class TestMaskInn:
    """Tests for INN masking."""

    def test_inn_10_digits(self):
        result = mask_inn("ИНН: 7701234567")
        assert result == "ИНН: 77******67"

    def test_inn_12_digits(self):
        result = mask_inn("ИНН физлица: 770123456789")
        assert result == "ИНН физлица: 77********89"

    def test_inn_embedded_in_text(self):
        result = mask_inn("Оплата от ИНН 7701234567 поступила")
        assert "77******67" in result
        assert "7701234567" not in result

    def test_no_inn_not_modified(self):
        text = "Код 12345 не является ИНН"
        result = mask_inn(text)
        assert result == text


class TestMaskPhone:
    """Tests for phone masking."""

    def test_phone_plus7(self):
        result = mask_phone("+79161234567")
        assert result == "+7******567"

    def test_phone_8_prefix(self):
        result = mask_phone("89161234567")
        assert result == "8******567"

    def test_phone_with_spaces(self):
        result = mask_phone("+7 916 123 45 67")
        assert "+7******" in result
        assert result.endswith("567")

    def test_phone_embedded_in_text(self):
        result = mask_phone("Позвоните по номеру +79161234567 для уточнения")
        assert "+7******567" in result
        assert "+79161234567" not in result

    def test_no_phone_not_modified(self):
        text = "Номер заказа 123456"
        result = mask_phone(text)
        assert result == text


class TestMaskAll:
    """Tests for combined masking."""

    def test_mask_all_combined(self):
        text = "Иванова Анна Петровна, ИНН 7701234567, тел +79161234567"
        result = mask_all(text)
        assert "Иванова" not in result
        assert "7701234567" not in result
        assert "+79161234567" not in result
        assert "И***ва А.П." in result
        assert "77******67" in result
        assert "+7******567" in result


class TestPiiProcessor:
    """Tests for structlog PII processor."""

    def test_processor_masks_event(self):
        event_dict = {
            "event": "User Иванова Анна Петровна logged in",
            "level": "info",
        }
        result = pii_processor(None, None, event_dict)
        assert "Иванова" not in result["event"]
        assert "И***ва А.П." in result["event"]

    def test_processor_masks_string_values(self):
        event_dict = {
            "event": "payment processed",
            "phone": "+79161234567",
            "inn": "7701234567",
        }
        result = pii_processor(None, None, event_dict)
        assert result["phone"] == "+7******567"
        assert result["inn"] == "77******67"

    def test_processor_ignores_non_string_values(self):
        event_dict = {
            "event": "test",
            "count": 42,
            "items": ["a", "b"],
        }
        result = pii_processor(None, None, event_dict)
        assert result["count"] == 42
        assert result["items"] == ["a", "b"]

    def test_processor_returns_event_dict(self):
        event_dict = {"event": "simple message"}
        result = pii_processor(None, None, event_dict)
        assert result is event_dict
