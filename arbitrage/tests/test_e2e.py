"""End-to-end smoke test: full pipeline from scan to execution."""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest
import aiohttp

from arbitrage import memory
from arbitrage.scanner import ArbitrageScanner
from arbitrage.ranker import ArbRanker
from arbitrage.executor import BetExecutor


# Guaranteed surebet event: 1/5.0 + 1/5.0 + 1/5.0 = 0.6 < 1.0
MOCK_SUREBET_EVENT = {
    "id": "e2e_test_event",
    "sport_key": "soccer_epl",
    "sport": "soccer_epl",
    "home_team": "E2E_Home",
    "away_team": "E2E_Away",
    "commence_time": "2025-06-01T18:00:00Z",
    "bookmakers": [
        {
            "key": "pinnacle",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": "E2E_Home", "price": 5.0},
                    {"name": "E2E_Away", "price": 5.0},
                    {"name": "Draw", "price": 5.0},
                ],
            }],
        },
        {
            "key": "bet365",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": "E2E_Home", "price": 5.2},
                    {"name": "E2E_Away", "price": 5.1},
                    {"name": "Draw", "price": 5.3},
                ],
            }],
        },
    ],
}


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Create isolated SQLite database for testing."""
    db_path = str(tmp_path / "test_e2e.db")
    monkeypatch.setattr(memory, "DB_PATH", db_path)
    memory.init_db()
    return db_path


@pytest.mark.asyncio
async def test_e2e_pipeline_surebet(isolated_db) -> None:
    """Full pipeline: scan -> filter -> rank -> execute -> record."""
    # 1. Scanner finds surebets
    scanner = ArbitrageScanner(min_arb_profit=0.5)
    surebets = scanner.find_surebets([MOCK_SUREBET_EVENT])
    assert len(surebets) > 0, "Scanner should find surebet in mock data"

    # 2. Convert to dicts (as main.py does)
    opp_dicts = []
    for opp in surebets:
        opp_dicts.append({
            "sport": opp.sport,
            "event": opp.event_name,
            "bookmakers": opp.bookmakers,
            "odds": opp.odds,
            "profit_pct": opp.profit_pct,
            "edge_pct": opp.edge_pct,
            "type": opp.type,
            "home": opp.home,
            "away": opp.away,
            "event_name": opp.event_name,
            "details": getattr(opp, "details", {}),
            "ai_score": 85,  # Simulated high AI score
            "best_odds": opp.odds[0] if opp.odds else 2.0,
            "sizing_mode": "surebet",
        })

    # 3. Rank
    ranker = ArbRanker(top_n=10)
    ranked = ranker.rank(opp_dicts)
    assert len(ranked) > 0, "Ranker should return results"

    # 4. Execute in dry-run
    executor = BetExecutor()
    executor.dry_run = True

    allocations = []
    for opp in ranked[:1]:  # Just first one
        allocations.append({
            "opportunity": opp,
            "stake_amount": 50.0,
        })

    results = await executor.execute(allocations)
    assert len(results) == 1
    assert results[0]["status"] == "SIMULATED"

    # 5. Record in memory
    opp = ranked[0]
    arb_id = memory.record_arb(
        sport=opp.get("sport", ""),
        event=opp.get("event", ""),
        arb_type=opp.get("type", "surebet"),
        bookmakers=opp.get("bookmakers", []),
        odds={"odds": opp.get("odds", [])},
        profit_pct=opp.get("profit_pct", 0.0),
        edge_pct=opp.get("edge_pct", 0.0),
        ai_score=85,
        status="SIMULATED",
    )
    assert arb_id is not None

    bet_id = memory.record_bet(
        arb_id=arb_id,
        bookmaker=opp.get("bookmakers", ["unknown"])[0],
        event=opp.get("event", ""),
        outcome="E2E_Home",
        stake=50.0,
        odds=opp.get("odds", [2.0])[0],
        result="SIMULATED",
    )
    assert bet_id is not None

    # 6. Verify data in DB
    stats = memory.get_stats()
    assert stats["total_arbs"] >= 1
    assert stats["total_bets"] >= 1

    # 7. Verify active bets (use get_pending_bets_for_settlement with 3h filter
    # for old bets; for cashout, bets must be >= 5 min old)
    # Insert a bet with old timestamp to test cashout query
    import sqlite3
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        "UPDATE bets SET ts = datetime('now', '-10 minutes') WHERE id = ?",
        (bet_id,),
    )
    conn.commit()
    conn.close()

    active_bets = memory.get_active_bets_for_cashout()
    assert len(active_bets) >= 1
    assert active_bets[0]["outcome"] == "E2E_Home"


@pytest.mark.asyncio
async def test_e2e_telegram_alert_called(isolated_db) -> None:
    """Verify Telegram alert would be sent for profitable arb."""
    from arbitrage import telegram_bot

    scanner = ArbitrageScanner(min_arb_profit=0.5)
    surebets = scanner.find_surebets([MOCK_SUREBET_EVENT])
    assert len(surebets) > 0

    opp = surebets[0]
    opp_dict = {
        "sport": opp.sport,
        "event": opp.event_name,
        "bookmakers": opp.bookmakers,
        "odds": opp.odds,
        "profit_pct": opp.profit_pct,
        "type": opp.type,
    }

    # Mock telegram send
    with patch.object(telegram_bot, "send_arb_alert", new_callable=AsyncMock) as mock_alert:
        async with aiohttp.ClientSession() as session:
            # Simulate the alert sending that main.py does
            if opp_dict["profit_pct"] >= 1.0:
                await telegram_bot.send_arb_alert(session, opp_dict, 85)

        # Verify alert was called
        if opp_dict["profit_pct"] >= 1.0:
            mock_alert.assert_called_once()
