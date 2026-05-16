"""Tests for pagination utility."""


from kindergarten_accountant_bot.utils.pagination import paginate_items


class TestPaginateItems:
    def test_small_list_no_navigation(self):
        """Lists with 5 or fewer items should not show navigation buttons."""
        items = [1, 2, 3]
        page_items, nav_buttons = paginate_items(items, page=0, page_size=5)
        assert page_items == [1, 2, 3]
        assert nav_buttons == []

    def test_exact_page_size_no_navigation(self):
        """List with exactly page_size items has no navigation."""
        items = [1, 2, 3, 4, 5]
        page_items, nav_buttons = paginate_items(items, page=0, page_size=5)
        assert page_items == [1, 2, 3, 4, 5]
        assert nav_buttons == []

    def test_seven_items_first_page(self):
        """7 items, first page shows 5 items with next button."""
        items = list(range(7))
        page_items, nav_buttons = paginate_items(items, page=0, page_size=5)
        assert page_items == [0, 1, 2, 3, 4]
        assert len(nav_buttons) == 1
        row = nav_buttons[0]
        # No prev button on first page, page indicator, next button
        assert len(row) == 2
        assert "1/2" in row[0].text
        assert row[1].callback_data == "page_1"

    def test_seven_items_second_page(self):
        """7 items, second page shows 2 items with prev button."""
        items = list(range(7))
        page_items, nav_buttons = paginate_items(items, page=1, page_size=5)
        assert page_items == [5, 6]
        assert len(nav_buttons) == 1
        row = nav_buttons[0]
        # Prev button, page indicator, no next button on last page
        assert len(row) == 2
        assert row[0].callback_data == "page_0"
        assert "2/2" in row[1].text

    def test_twelve_items_middle_page(self):
        """12 items, middle page shows prev, indicator, and next."""
        items = list(range(12))
        page_items, nav_buttons = paginate_items(items, page=1, page_size=5)
        assert page_items == [5, 6, 7, 8, 9]
        assert len(nav_buttons) == 1
        row = nav_buttons[0]
        assert len(row) == 3
        assert row[0].callback_data == "page_0"
        assert "2/3" in row[1].text
        assert row[2].callback_data == "page_2"

    def test_twelve_items_last_page(self):
        """12 items, last page shows only 2 items."""
        items = list(range(12))
        page_items, nav_buttons = paginate_items(items, page=2, page_size=5)
        assert page_items == [10, 11]
        assert len(nav_buttons) == 1
        row = nav_buttons[0]
        assert len(row) == 2
        assert row[0].callback_data == "page_1"
        assert "3/3" in row[1].text

    def test_custom_callback_prefix(self):
        """Custom callback prefix is used in button data."""
        items = list(range(7))
        page_items, nav_buttons = paginate_items(
            items, page=0, page_size=5, callback_prefix="page_ts_list"
        )
        row = nav_buttons[0]
        assert row[1].callback_data == "page_ts_list_1"

    def test_page_clamped_to_max(self):
        """Page number beyond max is clamped to last page."""
        items = list(range(7))
        page_items, nav_buttons = paginate_items(items, page=99, page_size=5)
        assert page_items == [5, 6]

    def test_page_clamped_to_zero(self):
        """Negative page number is clamped to 0."""
        items = list(range(7))
        page_items, nav_buttons = paginate_items(items, page=-5, page_size=5)
        assert page_items == [0, 1, 2, 3, 4]

    def test_empty_list(self):
        """Empty list returns empty results with no navigation."""
        page_items, nav_buttons = paginate_items([], page=0, page_size=5)
        assert page_items == []
        assert nav_buttons == []
