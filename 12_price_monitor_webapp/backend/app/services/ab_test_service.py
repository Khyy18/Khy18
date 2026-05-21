"""A/B test service - variant selection for posts and UI experiments."""
from __future__ import annotations


import hashlib
import logging

logger = logging.getLogger(__name__)

class ABTestService:
    """Manages A/B test variant assignment."""

    TESTS = {
        "post_format": {"variants": ["short", "detailed", "emoji"], "weights": [0.33, 0.34, 0.33]},
        "cta_button": {"variants": ["buy_now", "check_price", "view_deal"], "weights": [0.33, 0.34, 0.33]},
    }

    def get_variant(self, test_name: str, user_id: int) -> str:
        """Get deterministic variant for a user in a given test."""
        if test_name not in self.TESTS:
            return "control"

        test = self.TESTS[test_name]
        # Deterministic hash-based assignment
        hash_input = f"{test_name}:{user_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        bucket = (hash_value % 100) / 100.0

        cumulative = 0.0
        for variant, weight in zip(test["variants"], test["weights"]):
            cumulative += weight
            if bucket < cumulative:
                return variant
        return test["variants"][-1]

    def get_all_variants(self, user_id: int) -> dict[str, str]:
        """Get all test variants for a user."""
        return {
            test_name: self.get_variant(test_name, user_id)
            for test_name in self.TESTS
        }

ab_test_service = ABTestService()
