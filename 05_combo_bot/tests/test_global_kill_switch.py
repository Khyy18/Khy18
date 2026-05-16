"""Тесты global_kill_switch.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capital_allocator
import global_kill_switch


def _make_state() -> dict:
    state: dict = {}
    capital_allocator.init_allocator_state(state)
    return state


def test_no_kill_initially():
    """Kill-switch не активен при старте."""
    state = _make_state()
    assert not global_kill_switch.is_kill_active(state)
    assert not global_kill_switch.check_global_kill(state)


def test_kill_triggers_on_drawdown():
    """Kill срабатывает при drawdown >= 15%."""
    state = _make_state()
    # HWM = 550, порог 15% = убыток 82.5
    capital_allocator.record_pnl(state, "grid", -85.0)
    # equity = 465, dd = (550-465)/550 = 0.1545 > 0.15
    triggered = global_kill_switch.check_global_kill(state)
    assert triggered
    assert global_kill_switch.is_kill_active(state)
    assert "15" in global_kill_switch.get_kill_reason(state)


def test_kill_does_not_trigger_below_threshold():
    """Kill НЕ срабатывает при drawdown < 15%."""
    state = _make_state()
    # Убыток 70 из 550 = 12.7% < 15%
    capital_allocator.record_pnl(state, "grid", -70.0)
    triggered = global_kill_switch.check_global_kill(state)
    assert not triggered
    assert not global_kill_switch.is_kill_active(state)


def test_manual_activate():
    """Ручная активация через Telegram."""
    state = _make_state()
    msg = global_kill_switch.manual_activate(state, "тест")
    assert "активирован" in msg.lower()
    assert global_kill_switch.is_kill_active(state)
    assert "тест" in global_kill_switch.get_kill_reason(state)


def test_manual_resume():
    """Ручное снятие kill-switch."""
    state = _make_state()
    global_kill_switch.manual_activate(state, "test")
    assert global_kill_switch.is_kill_active(state)

    msg = global_kill_switch.manual_resume(state)
    assert "снят" in msg.lower()
    assert not global_kill_switch.is_kill_active(state)
    # HWM сброшен на текущий equity
    assert state["global"]["hwm_equity"] == capital_allocator.get_current_equity(state)


def test_resume_when_not_active():
    """Снятие не-активного kill — информационное сообщение."""
    state = _make_state()
    msg = global_kill_switch.manual_resume(state)
    assert "не активен" in msg.lower()


def test_kill_stays_active_on_recheck():
    """После активации повторный check не меняет состояние."""
    state = _make_state()
    global_kill_switch.manual_activate(state, "x")
    # Повторная проверка
    result = global_kill_switch.check_global_kill(state)
    assert result  # всё ещё активен
    assert global_kill_switch.is_kill_active(state)


def test_get_status():
    """get_status возвращает полную информацию."""
    state = _make_state()
    status = global_kill_switch.get_status(state)
    assert "active" in status
    assert "reason" in status
    assert "drawdown_pct" in status
    assert "threshold_pct" in status
    assert "equity" in status
    assert "hwm" in status
    assert "margin_to_kill" in status
    assert status["threshold_pct"] == 0.15


# ─── Kill file tests ───────────────────────────────────────────────────


def test_kill_file_activates_kill(tmp_path, monkeypatch):
    """Touch KILL file triggers is_kill_active and check_global_kill."""
    kill_file = str(tmp_path / "KILL")
    monkeypatch.setattr(global_kill_switch, "KILL_FILE_PATH", kill_file)

    state = {"global": {"global_kill_active": False}}
    monkeypatch.setattr(capital_allocator, "get_drawdown_pct", lambda s: 0.0)
    monkeypatch.setattr(capital_allocator, "get_current_equity", lambda s: 1000.0)

    # No file = not active
    assert global_kill_switch.is_kill_active(state) is False
    assert global_kill_switch.check_global_kill(state) is False

    # Create kill file
    open(kill_file, 'w').close()

    # Now should be active
    assert global_kill_switch.is_kill_active(state) is True
    assert global_kill_switch.check_global_kill(state) is True
    assert state["global"]["global_kill_active"] is True


def test_kill_file_absent_not_active(tmp_path, monkeypatch):
    """Without kill file, is_kill_active returns False (only checks state)."""
    kill_file = str(tmp_path / "KILL_NONEXISTENT")
    monkeypatch.setattr(global_kill_switch, "KILL_FILE_PATH", kill_file)

    state = {"global": {"global_kill_active": False}}
    assert global_kill_switch.is_kill_active(state) is False
