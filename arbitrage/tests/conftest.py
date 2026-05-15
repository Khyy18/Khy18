"""Shared fixtures for arbitrage test suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def mock_event() -> dict:
    """Single event with two bookmakers providing h2h odds."""
    return {
        "id": "evt1",
        "sport": "soccer_epl",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "commence_time": "2024-01-01T15:00:00Z",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.10},
                            {"name": "Chelsea", "price": 3.50},
                            {"name": "Draw", "price": 3.20},
                        ],
                    }
                ],
            },
            {
                "key": "bet365",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.05},
                            {"name": "Chelsea", "price": 3.40},
                            {"name": "Draw", "price": 3.10},
                        ],
                    }
                ],
            },
        ],
    }


@pytest.fixture
def mock_events_list() -> list:
    """List of 3 events with different odds."""
    return [
        {
            "id": "evt1",
            "sport": "soccer_epl",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "commence_time": "2024-01-01T15:00:00Z",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Arsenal", "price": 2.10},
                                {"name": "Chelsea", "price": 3.50},
                                {"name": "Draw", "price": 3.20},
                            ],
                        }
                    ],
                },
                {
                    "key": "bet365",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Arsenal", "price": 2.15},
                                {"name": "Chelsea", "price": 3.40},
                                {"name": "Draw", "price": 3.10},
                            ],
                        }
                    ],
                },
            ],
        },
        {
            "id": "evt2",
            "sport": "basketball_nba",
            "home_team": "Lakers",
            "away_team": "Warriors",
            "commence_time": "2024-01-02T20:00:00Z",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Lakers", "price": 1.80},
                                {"name": "Warriors", "price": 2.10},
                            ],
                        }
                    ],
                },
                {
                    "key": "unibet",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Lakers", "price": 1.85},
                                {"name": "Warriors", "price": 2.05},
                            ],
                        }
                    ],
                },
            ],
        },
        {
            "id": "evt3",
            "sport": "tennis_atp",
            "home_team": "Djokovic",
            "away_team": "Alcaraz",
            "commence_time": "2024-01-03T12:00:00Z",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Djokovic", "price": 1.60},
                                {"name": "Alcaraz", "price": 2.40},
                            ],
                        }
                    ],
                },
                {
                    "key": "marathonbet",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Djokovic", "price": 1.65},
                                {"name": "Alcaraz", "price": 2.35},
                            ],
                        }
                    ],
                },
            ],
        },
    ]


@pytest.fixture
def sample_surebet_event() -> dict:
    """Event where inverse_sum < 1.0 (guaranteed arb)."""
    # 1/5.0 + 1/5.0 + 1/5.0 = 0.6 < 1.0 -> arb exists
    return {
        "id": "arb_evt",
        "sport": "soccer_epl",
        "home_team": "TeamA",
        "away_team": "TeamB",
        "commence_time": "2024-06-01T18:00:00Z",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "TeamA", "price": 5.0},
                            {"name": "TeamB", "price": 3.0},
                            {"name": "Draw", "price": 2.5},
                        ],
                    }
                ],
            },
            {
                "key": "bet365",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "TeamA", "price": 4.8},
                            {"name": "TeamB", "price": 5.5},
                            {"name": "Draw", "price": 5.2},
                        ],
                    }
                ],
            },
        ],
    }


@pytest.fixture
def sample_value_event() -> dict:
    """Event with sharp_probs where edge > 3% for at least one outcome."""
    return {
        "id": "val_evt",
        "sport": "soccer_epl",
        "home_team": "ValTeamA",
        "away_team": "ValTeamB",
        "commence_time": "2024-06-01T18:00:00Z",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "ValTeamA", "price": 2.0},
                            {"name": "ValTeamB", "price": 3.0},
                            {"name": "Draw", "price": 4.0},
                        ],
                    }
                ],
            },
            {
                "key": "bet365",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "ValTeamA", "price": 2.50},
                            {"name": "ValTeamB", "price": 3.20},
                            {"name": "Draw", "price": 4.10},
                        ],
                    }
                ],
            },
        ],
    }
