"""Тесты circuit_breaker: state-machine CLOSED → OPEN → HALF_OPEN → CLOSED."""

import time

import circuit_breaker as cb


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        b = cb.CircuitBreaker()
        assert not b.is_open("bybit")

    def test_threshold_opens_breaker(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=3, cooldown_sec=10)
        for _ in range(3):
            b.record_failure("bybit", "timeout")
        assert b.is_open("bybit")

    def test_below_threshold_stays_closed(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=5, cooldown_sec=10)
        for _ in range(4):
            b.record_failure("bybit", "timeout")
        assert not b.is_open("bybit")

    def test_success_resets_failures(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=3, cooldown_sec=10)
        for _ in range(2):
            b.record_failure("bybit", "timeout")
        b.record_success("bybit")
        # Ещё 2 failures - всё ещё под порогом, потому что после success сбросили.
        b.record_failure("bybit", "timeout")
        b.record_failure("bybit", "timeout")
        assert not b.is_open("bybit")

    def test_cooldown_transitions_to_half_open(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=2, cooldown_sec=0.05)
        for _ in range(2):
            b.record_failure("bybit", "timeout")
        assert b.is_open("bybit")
        time.sleep(0.06)
        # is_open проверка переводит в HALF_OPEN если cooldown истёк.
        assert not b.is_open("bybit")

    def test_half_open_failure_reopens(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=2, cooldown_sec=0.05)
        for _ in range(2):
            b.record_failure("bybit", "timeout")
        time.sleep(0.06)
        b.is_open("bybit")  # переход в HALF_OPEN
        b.record_failure("bybit", "still failing")
        assert b.is_open("bybit")

    def test_half_open_success_closes(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=2, cooldown_sec=0.05)
        for _ in range(2):
            b.record_failure("bybit", "timeout")
        time.sleep(0.06)
        b.is_open("bybit")  # → HALF_OPEN
        b.record_success("bybit")
        assert not b.is_open("bybit")
        # Дальше — CLOSED, можем накапливать ошибки сначала.
        b.record_failure("bybit", "x")
        assert not b.is_open("bybit")

    def test_per_exchange_isolation(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=2, cooldown_sec=10)
        for _ in range(2):
            b.record_failure("bybit", "timeout")
        assert b.is_open("bybit")
        assert not b.is_open("okx")  # okx не пострадал

    def test_window_expires_old_failures(self):
        b = cb.CircuitBreaker(window_sec=0.05, fail_threshold=3, cooldown_sec=10)
        b.record_failure("bybit", "x")
        time.sleep(0.06)
        # Старая ошибка вышла из окна.
        b.record_failure("bybit", "x")
        b.record_failure("bybit", "x")
        # Только 2 свежих, ниже порога.
        assert not b.is_open("bybit")

    def test_status_snapshot_format(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=2, cooldown_sec=10)
        b.record_failure("bybit", "fail-msg")
        snap = b.status_snapshot()
        assert "bybit" in snap
        assert snap["bybit"]["state"] == "CLOSED"
        assert snap["bybit"]["last_failure_msg"] == "fail-msg"

    def test_reset(self):
        b = cb.CircuitBreaker(window_sec=60, fail_threshold=2, cooldown_sec=10)
        for _ in range(2):
            b.record_failure("bybit", "x")
        assert b.is_open("bybit")
        b.reset("bybit")
        assert not b.is_open("bybit")
