"""Tests for SteamDetector from arbitrage.steam_moves."""

from __future__ import annotations

import time

from arbitrage.steam_moves import MAX_HISTORY_AGE_SEC, STEAM_THRESHOLD, SteamDetector


class TestSteamDetector:
    """Tests for SteamDetector."""

    def test_update_sharp_snapshot(self) -> None:
        """Stores pinnacle data into sharp history."""
        detector = SteamDetector()
        events = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.0},
                            {"name": "B", "price": 3.5},
                        ]}],
                    }
                ],
            }
        ]
        detector.update_sharp_snapshot(events)
        assert "e1::A" in detector._sharp_history
        assert "e1::B" in detector._sharp_history
        assert len(detector._sharp_history["e1::A"]) == 1
        assert detector._sharp_history["e1::A"][0][1] == 2.0

    def test_detect_steam_finds_stale(self) -> None:
        """After sharp movement, soft bookmaker is detected as stale."""
        detector = SteamDetector()

        # First snapshot: Pinnacle at 2.0
        events_v1 = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.0},
                            {"name": "B", "price": 3.5},
                        ]}],
                    },
                    {
                        "key": "bet365",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.0},
                            {"name": "B", "price": 3.5},
                        ]}],
                    },
                ],
            }
        ]
        detector.update_sharp_snapshot(events_v1)

        # Second snapshot: Pinnacle moved significantly (to 1.50 -> prob change > 0.03)
        # 1/2.0 = 0.5, 1/1.50 = 0.667, movement = 0.167 > STEAM_THRESHOLD
        events_v2 = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 1.50},
                            {"name": "B", "price": 3.5},
                        ]}],
                    },
                    {
                        "key": "bet365",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.0},  # Still at old odds
                            {"name": "B", "price": 3.5},
                        ]}],
                    },
                ],
            }
        ]
        detector.update_sharp_snapshot(events_v2)

        result = detector.detect_steam(events_v2, {})
        assert len(result) >= 1
        opp = result[0]
        assert opp.event_name == "A vs B"
        assert len(opp.stale_bookmakers) >= 1
        assert opp.stale_bookmakers[0]["bookmaker"] == "bet365"

    def test_detect_steam_ignores_small_movement(self) -> None:
        """Movement < STEAM_THRESHOLD is ignored."""
        detector = SteamDetector()

        events_v1 = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.00},
                        ]}],
                    },
                ],
            }
        ]
        detector.update_sharp_snapshot(events_v1)

        # Small movement: 2.00 -> 1.98 (prob change ~0.005 < 0.03)
        events_v2 = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 1.98},
                        ]}],
                    },
                    {
                        "key": "bet365",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.00},
                        ]}],
                    },
                ],
            }
        ]
        detector.update_sharp_snapshot(events_v2)

        result = detector.detect_steam(events_v2, {})
        assert result == []

    def test_detect_steam_no_history(self) -> None:
        """No detection without prior snapshot (needs at least 2 history entries)."""
        detector = SteamDetector()
        events = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 1.50},
                        ]}],
                    },
                    {
                        "key": "bet365",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.00},
                        ]}],
                    },
                ],
            }
        ]
        # Only one snapshot - not enough history
        detector.update_sharp_snapshot(events)
        result = detector.detect_steam(events, {})
        assert result == []

    def test_prune_stale_keys(self) -> None:
        """Old entries are removed by _prune_stale_keys."""
        detector = SteamDetector()
        # Manually insert old entry
        old_ts = time.time() - MAX_HISTORY_AGE_SEC - 100
        detector._sharp_history["old_key::A"] = [(old_ts, 2.0)]
        detector._sharp_history["fresh_key::B"] = [(time.time(), 3.0)]

        detector._prune_stale_keys()

        assert "old_key::A" not in detector._sharp_history
        assert "fresh_key::B" in detector._sharp_history
