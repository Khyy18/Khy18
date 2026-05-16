import pytest
import pytest_asyncio

from kindergarten_accountant_bot.config import BASE_FEE_PER_DAY
from kindergarten_accountant_bot.models.child import (
    add_child,
    delete_child,
    get_child,
    get_children,
    get_children_by_group,
)
from kindergarten_accountant_bot.models.payment import (
    create_fee_record,
    get_debts,
    get_payment_record,
    record_payment,
)


@pytest.mark.asyncio
class TestChild:
    async def test_add_child_returns_id(self, test_db):
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        assert child_id is not None
        assert child_id > 0

    async def test_add_child_with_discount(self, test_db):
        child_id = await add_child("Иванов Саша", "Звёздочки", "Иванова М.А.", 50)
        child = await get_child(child_id)
        assert child is not None
        assert child["discount_percent"] == 50

    async def test_get_children(self, test_db):
        await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await add_child("Иванов Саша", "Звёздочки", "Иванова М.А.", 50)
        children = await get_children()
        assert len(children) == 2

    async def test_delete_child(self, test_db):
        child_id = await add_child("Удаляемый Р.", "Тест", "Родитель", 0)
        result = await delete_child(child_id)
        assert result is True
        child = await get_child(child_id)
        assert child is None

    async def test_get_children_by_group(self, test_db):
        await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await add_child("Сидоров Коля", "Солнышко", "Сидорова Л.А.", 0)
        await add_child("Иванов Саша", "Звёздочки", "Иванова М.А.", 50)
        group = await get_children_by_group("Солнышко")
        assert len(group) == 2


@pytest.mark.asyncio
class TestFeeCalculation:
    async def test_fee_no_discount(self, test_db):
        """20 days, 0% discount = 3000."""
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        days = 20
        fee = BASE_FEE_PER_DAY * days * (1 - 0 / 100)
        assert fee == 3000.0
        record_id = await create_fee_record(child_id, 1, 2025, days, fee)
        assert record_id > 0

    async def test_fee_50_percent_discount(self, test_db):
        """18 days, 50% discount = 1350."""
        child_id = await add_child("Иванов Саша", "Звёздочки", "Иванова М.А.", 50)
        days = 18
        fee = BASE_FEE_PER_DAY * days * (1 - 50 / 100)
        assert fee == 1350.0
        await create_fee_record(child_id, 1, 2025, days, fee)

    async def test_fee_100_percent_discount(self, test_db):
        """22 days, 100% discount = 0."""
        child_id = await add_child("Льготный Д.", "Группа", "Родитель", 100)
        days = 22
        fee = BASE_FEE_PER_DAY * days * (1 - 100 / 100)
        assert fee == 0.0
        await create_fee_record(child_id, 1, 2025, days, fee)


@pytest.mark.asyncio
class TestPayment:
    async def test_create_fee_record_and_get(self, test_db):
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await create_fee_record(child_id, 1, 2025, 20, 3000.0)
        record = await get_payment_record(child_id, 1, 2025)
        assert record is not None
        assert record["amount_due"] == 3000.0
        assert record["amount_paid"] == 0

    async def test_record_payment(self, test_db):
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await create_fee_record(child_id, 1, 2025, 20, 3000.0)
        await record_payment(child_id, 1, 2025, 1500.0)
        record = await get_payment_record(child_id, 1, 2025)
        assert record["amount_paid"] == 1500.0

    async def test_record_payment_multiple(self, test_db):
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await create_fee_record(child_id, 1, 2025, 20, 3000.0)
        await record_payment(child_id, 1, 2025, 1000.0)
        await record_payment(child_id, 1, 2025, 500.0)
        record = await get_payment_record(child_id, 1, 2025)
        assert record["amount_paid"] == 1500.0

    async def test_get_debts_returns_only_unpaid(self, test_db):
        child1 = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        child2 = await add_child("Иванов Саша", "Звёздочки", "Иванова М.А.", 0)
        await create_fee_record(child1, 1, 2025, 20, 3000.0)
        await create_fee_record(child2, 1, 2025, 18, 2700.0)
        # Pay child1 in full
        await record_payment(child1, 1, 2025, 3000.0)
        # Child2 remains unpaid
        debts = await get_debts()
        assert len(debts) == 1
        assert debts[0]["child_fio"] == "Иванов Саша"

    async def test_get_debts_partial_payment(self, test_db):
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await create_fee_record(child_id, 1, 2025, 20, 3000.0)
        await record_payment(child_id, 1, 2025, 1000.0)
        debts = await get_debts()
        assert len(debts) == 1
        assert debts[0]["amount_due"] - debts[0]["amount_paid"] == 2000.0

    async def test_create_fee_record_updates_existing(self, test_db):
        child_id = await add_child("Петров Миша", "Солнышко", "Петрова Е.В.", 0)
        await create_fee_record(child_id, 1, 2025, 18, 2700.0)
        await create_fee_record(child_id, 1, 2025, 20, 3000.0)
        record = await get_payment_record(child_id, 1, 2025)
        assert record["amount_due"] == 3000.0
        assert record["attendance_days"] == 20
