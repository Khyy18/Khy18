import pytest

from kindergarten_accountant_bot.handlers.salary import calculate_salary
from kindergarten_accountant_bot.handlers.vacation import calculate_vacation
from kindergarten_accountant_bot.handlers.sick import calculate_sick


class TestSalaryCalculation:
    def test_basic_salary_30000_rate1_stazh10(self):
        result = calculate_salary(oklad=30000, rate=1.0, stazh_percent=10)
        assert result["nachisleno"] == pytest.approx(33000.0)
        assert result["ndfl"] == pytest.approx(4290.0)
        assert result["na_ruki"] == pytest.approx(28710.0)
        assert result["pfr"] == pytest.approx(7260.0)
        assert result["oms"] == pytest.approx(1683.0)
        assert result["fss"] == pytest.approx(957.0)
        assert result["fss_ns"] == pytest.approx(66.0)
        assert result["total_contributions"] == pytest.approx(9966.0)

    def test_salary_25000_rate05_stazh0(self):
        result = calculate_salary(oklad=25000, rate=0.5, stazh_percent=0)
        assert result["nachisleno"] == pytest.approx(12500.0)
        assert result["ndfl"] == pytest.approx(1625.0)
        assert result["na_ruki"] == pytest.approx(10875.0)

    def test_salary_rate025(self):
        result = calculate_salary(oklad=40000, rate=0.25, stazh_percent=20)
        nachisleno = 40000 * 0.25 * 1.2
        assert result["nachisleno"] == pytest.approx(nachisleno)
        assert result["ndfl"] == pytest.approx(nachisleno * 0.13)
        assert result["na_ruki"] == pytest.approx(nachisleno - nachisleno * 0.13)

    def test_salary_zero_stazh(self):
        result = calculate_salary(oklad=50000, rate=1.0, stazh_percent=0)
        assert result["nachisleno"] == pytest.approx(50000.0)
        assert result["na_ruki"] == pytest.approx(50000 - 50000 * 0.13)

    def test_salary_with_category_percent(self):
        result = calculate_salary(oklad=30000, rate=1.0, stazh_percent=10, category_percent=15)
        # nachisleno = 30000 * 1.0 * (1 + 10/100 + 15/100) = 30000 * 1.25 = 37500
        assert result["nachisleno"] == pytest.approx(37500.0)
        assert result["ndfl"] == pytest.approx(37500 * 0.13)
        assert result["na_ruki"] == pytest.approx(37500 - 37500 * 0.13)

    def test_salary_category_percent_default_zero(self):
        # Without category_percent, should behave the same as before
        result_without = calculate_salary(oklad=30000, rate=1.0, stazh_percent=10)
        result_with_zero = calculate_salary(oklad=30000, rate=1.0, stazh_percent=10, category_percent=0)
        assert result_without["nachisleno"] == result_with_zero["nachisleno"]


class TestVacationCalculation:
    def test_vacation_600000_28days(self):
        result = calculate_vacation(total_12_months=600000, days=28)
        avg_daily = 600000 / 12 / 29.3
        gross = avg_daily * 28
        ndfl = gross * 0.13
        net = gross - ndfl
        assert result["avg_daily"] == pytest.approx(avg_daily, rel=1e-5)
        assert result["vacation_gross"] == pytest.approx(gross, rel=1e-5)
        assert result["ndfl"] == pytest.approx(ndfl, rel=1e-5)
        assert result["vacation_net"] == pytest.approx(net, rel=1e-5)

    def test_vacation_avg_monthly(self):
        result = calculate_vacation(total_12_months=360000, days=14)
        assert result["avg_monthly"] == pytest.approx(30000.0)
        assert result["avg_daily"] == pytest.approx(30000 / 29.3, rel=1e-5)

    def test_vacation_single_day(self):
        result = calculate_vacation(total_12_months=120000, days=1)
        avg_daily = 120000 / 12 / 29.3
        assert result["vacation_gross"] == pytest.approx(avg_daily, rel=1e-5)


class TestSickCalculation:
    def test_sick_less_than_5_years(self):
        result = calculate_sick(earnings_2y=1000000, stazh_bracket="<5", days=10)
        daily = (1000000 / 730) * 0.60
        total_gross = daily * 10
        ndfl = total_gross * 0.13
        total_net = total_gross - ndfl
        assert result["percent"] == 0.60
        assert result["daily"] == pytest.approx(daily, rel=1e-5)
        assert result["total_gross"] == pytest.approx(total_gross, rel=1e-5)
        assert result["ndfl"] == pytest.approx(ndfl, rel=1e-5)
        assert result["total_net"] == pytest.approx(total_net, rel=1e-5)

    def test_sick_5_to_8_years(self):
        result = calculate_sick(earnings_2y=1000000, stazh_bracket="5-8", days=10)
        daily = (1000000 / 730) * 0.80
        total_gross = daily * 10
        assert result["percent"] == 0.80
        assert result["daily"] == pytest.approx(daily, rel=1e-5)
        assert result["total_gross"] == pytest.approx(total_gross, rel=1e-5)

    def test_sick_more_than_8_years(self):
        result = calculate_sick(earnings_2y=1000000, stazh_bracket=">8", days=10)
        daily = (1000000 / 730) * 1.00
        total_gross = daily * 10
        ndfl = total_gross * 0.13
        total_net = total_gross - ndfl
        assert result["percent"] == 1.00
        assert result["daily"] == pytest.approx(daily, rel=1e-5)
        assert result["total_gross"] == pytest.approx(total_gross, rel=1e-5)
        assert result["total_net"] == pytest.approx(total_net, rel=1e-5)

    def test_sick_specific_values_less_5(self):
        # daily = 1000000/730*0.6 = 821.917808...
        # total = 821.917808... * 10 = 8219.178...
        result = calculate_sick(earnings_2y=1000000, stazh_bracket="<5", days=10)
        assert result["daily"] == pytest.approx(821.9178, rel=1e-4)
        assert result["total_gross"] == pytest.approx(8219.178, rel=1e-4)

    def test_sick_specific_values_more_8(self):
        # daily = 1000000/730*1.0 = 1369.863...
        # total = 1369.863... * 10 = 13698.63...
        result = calculate_sick(earnings_2y=1000000, stazh_bracket=">8", days=10)
        assert result["daily"] == pytest.approx(1369.863, rel=1e-4)
        assert result["total_gross"] == pytest.approx(13698.63, rel=1e-4)
