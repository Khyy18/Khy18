"""Tests for KBK reference data and search functionality."""


from kindergarten_accountant_bot.data.kbk_codes import KBK_CODES, POPULAR_KBK, search_kbk


def test_kbk_codes_has_at_least_30_entries():
    """KBK_CODES should contain at least 30 entries."""
    assert len(KBK_CODES) >= 30


def test_kbk_codes_structure():
    """Each KBK entry should have required fields."""
    for entry in KBK_CODES:
        assert "code" in entry
        assert "short_name" in entry
        assert "description" in entry
        assert "kvr" in entry


def test_search_kbk_finds_ndfl():
    """Search should find NDFL-related entries."""
    results = search_kbk("НДФЛ")
    assert len(results) >= 1
    assert any("НДФЛ" in r["short_name"] or "НДФЛ" in r["description"] for r in results)


def test_search_kbk_finds_by_partial_code():
    """Search should find entries by partial code."""
    results = search_kbk("182 1 01")
    assert len(results) >= 1


def test_search_kbk_case_insensitive():
    """Search should be case-insensitive."""
    results_upper = search_kbk("ПФР")
    results_lower = search_kbk("пфр")
    assert results_upper == results_lower
    assert len(results_upper) >= 1


def test_search_kbk_empty_result():
    """Search for nonsense query should return empty."""
    results = search_kbk("xyz123nonsense")
    assert results == []


def test_popular_kbk_subset():
    """POPULAR_KBK should be a subset of KBK_CODES."""
    for entry in POPULAR_KBK:
        assert entry in KBK_CODES


def test_popular_kbk_has_entries():
    """POPULAR_KBK should have entries."""
    assert len(POPULAR_KBK) == 10
