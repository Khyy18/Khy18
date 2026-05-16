"""Tests for ArbDeduplicator from arbitrage.dedup."""

from __future__ import annotations

import time

from arbitrage.dedup import ArbDeduplicator


class TestArbDeduplicator:
    """Tests for ArbDeduplicator."""

    def test_new_opportunity_not_duplicate(self) -> None:
        """Fresh opportunity returns False for is_duplicate."""
        dedup = ArbDeduplicator()
        opp = {"home": "Arsenal", "away": "Chelsea", "type": "surebet", "details": {"market": "h2h"}}
        assert dedup.is_duplicate(opp) is False

    def test_marked_is_duplicate(self) -> None:
        """After mark_executed, is_duplicate returns True."""
        dedup = ArbDeduplicator()
        opp = {"home": "Arsenal", "away": "Chelsea", "type": "surebet", "details": {"market": "h2h"}}
        dedup.mark_executed(opp)
        assert dedup.is_duplicate(opp) is True

    def test_different_events_not_duplicate(self) -> None:
        """Different home/away teams are not matched as duplicates."""
        dedup = ArbDeduplicator()
        opp1 = {"home": "Arsenal", "away": "Chelsea", "type": "surebet", "details": {"market": "h2h"}}
        opp2 = {"home": "Liverpool", "away": "ManCity", "type": "surebet", "details": {"market": "h2h"}}
        dedup.mark_executed(opp1)
        assert dedup.is_duplicate(opp2) is False

    def test_ttl_expiry(self) -> None:
        """With TTL=0.1 seconds, entry expires after sleep."""
        dedup = ArbDeduplicator(ttl_sec=0.1)
        opp = {"home": "Arsenal", "away": "Chelsea", "type": "surebet", "details": {"market": "h2h"}}
        dedup.mark_executed(opp)
        assert dedup.is_duplicate(opp) is True
        time.sleep(0.15)
        assert dedup.is_duplicate(opp) is False
