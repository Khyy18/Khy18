import pytest

from kindergarten_accountant_bot.models.employee import (
    add_employee,
    delete_employee,
    get_employee,
    get_employees,
)
from kindergarten_accountant_bot.models.timesheet import (
    add_mark,
    get_marks_for_month,
    get_monthly_summary,
)


@pytest.mark.asyncio
class TestEmployee:
    async def test_add_employee_returns_id(self, test_db):
        emp_id = await add_employee("Иванова А.И.", "Воспитатель", 1.0)
        assert emp_id is not None
        assert emp_id > 0

    async def test_get_employees_returns_list(self, test_db):
        await add_employee("Иванова А.И.", "Воспитатель", 1.0)
        await add_employee("Петрова М.С.", "Няня", 0.5)
        employees = await get_employees()
        assert len(employees) == 2
        assert employees[0]["fio"] == "Иванова А.И."
        assert employees[1]["fio"] == "Петрова М.С."

    async def test_get_employee_by_id(self, test_db):
        emp_id = await add_employee("Сидорова Л.В.", "Повар", 0.75)
        emp = await get_employee(emp_id)
        assert emp is not None
        assert emp["fio"] == "Сидорова Л.В."
        assert emp["position"] == "Повар"
        assert emp["rate"] == 0.75

    async def test_get_employee_not_found(self, test_db):
        emp = await get_employee(999)
        assert emp is None

    async def test_delete_employee(self, test_db):
        emp_id = await add_employee("Удаляемая А.Б.", "Тест", 1.0)
        result = await delete_employee(emp_id)
        assert result is True
        emp = await get_employee(emp_id)
        assert emp is None

    async def test_delete_employee_not_found(self, test_db):
        result = await delete_employee(999)
        assert result is False


@pytest.mark.asyncio
class TestTimesheet:
    async def test_add_mark(self, test_db):
        emp_id = await add_employee("Иванова А.И.", "Воспитатель", 1.0)
        mark_id = await add_mark(emp_id, "2025-01-15", "Я")
        assert mark_id is not None
        assert mark_id > 0

    async def test_add_mark_updates_existing(self, test_db):
        emp_id = await add_employee("Иванова А.И.", "Воспитатель", 1.0)
        mark_id1 = await add_mark(emp_id, "2025-01-15", "Я")
        mark_id2 = await add_mark(emp_id, "2025-01-15", "Б")
        assert mark_id1 == mark_id2
        marks = await get_marks_for_month(emp_id, 2025, 1)
        assert len(marks) == 1
        assert marks[0]["mark_type"] == "Б"

    async def test_get_marks_for_month(self, test_db):
        emp_id = await add_employee("Иванова А.И.", "Воспитатель", 1.0)
        await add_mark(emp_id, "2025-01-10", "Я")
        await add_mark(emp_id, "2025-01-11", "Я")
        await add_mark(emp_id, "2025-02-01", "Я")
        marks = await get_marks_for_month(emp_id, 2025, 1)
        assert len(marks) == 2

    async def test_get_monthly_summary(self, test_db):
        emp_id = await add_employee("Иванова А.И.", "Воспитатель", 1.0)
        for day in range(1, 19):
            await add_mark(emp_id, f"2025-01-{day:02d}", "Я")
        await add_mark(emp_id, "2025-01-19", "Б")
        await add_mark(emp_id, "2025-01-20", "Б")
        await add_mark(emp_id, "2025-01-21", "ОТ")
        summary = await get_monthly_summary(emp_id, 2025, 1)
        assert summary["Я"] == 18
        assert summary["Б"] == 2
        assert summary["О"] == 0
        assert summary["ОТ"] == 1
        assert summary["П"] == 0
