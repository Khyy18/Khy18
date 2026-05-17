"""Smoke test script for the AI Outbound Sales platform.

Usage:
    BASE_URL=http://localhost:8000 python scripts/smoke_test.py

Tests core endpoints sequentially and reports PASS/FAIL with response times.
Exit code 0 if all pass, 1 otherwise.
"""

import os
import sys
import time
import uuid

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
TIMEOUT = 30.0

# Test credentials
TEST_EMAIL = f"smoke-{uuid.uuid4().hex[:8]}@smoketest.com"
TEST_PASSWORD = "smoke_test_pass_123"
TEST_TENANT = "Smoke Test Corp"


def _print_result(endpoint: str, passed: bool, elapsed_ms: float, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    msg = f"[{status}] {endpoint} ({elapsed_ms:.0f}ms)"
    if detail:
        msg += f" - {detail}"
    print(msg)


def run_smoke_tests() -> bool:
    """Run all smoke tests. Returns True if all pass."""
    results = []
    token = None

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # 1. Health check
        start = time.time()
        try:
            resp = client.get("/health")
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            _print_result("GET /health", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("GET /health", False, elapsed, str(e))
            results.append(False)

        # 2. Register
        start = time.time()
        try:
            resp = client.post(
                "/api/auth/register",
                json={
                    "email": TEST_EMAIL,
                    "password": TEST_PASSWORD,
                    "tenant_name": TEST_TENANT,
                },
            )
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 201
            _print_result("POST /api/auth/register", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("POST /api/auth/register", False, elapsed, str(e))
            results.append(False)

        # 3. Login
        start = time.time()
        try:
            resp = client.post(
                "/api/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            )
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            if passed:
                token = resp.json().get("access_token")
            _print_result("POST /api/auth/login", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("POST /api/auth/login", False, elapsed, str(e))
            results.append(False)

        if not token:
            print("\nCannot continue without auth token.")
            return False

        headers = {"Authorization": f"Bearer {token}"}

        # 4. Campaigns list
        start = time.time()
        try:
            resp = client.get("/api/campaigns/", headers=headers)
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            _print_result("GET /api/campaigns/", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("GET /api/campaigns/", False, elapsed, str(e))
            results.append(False)

        # 5. Leads list
        start = time.time()
        try:
            resp = client.get("/api/leads/", headers=headers)
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            _print_result("GET /api/leads/", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("GET /api/leads/", False, elapsed, str(e))
            results.append(False)

        # 6. Voice stats
        start = time.time()
        try:
            resp = client.get("/api/voice/stats", headers=headers)
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            _print_result("GET /api/voice/stats", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("GET /api/voice/stats", False, elapsed, str(e))
            results.append(False)

        # 7. Analytics funnel
        start = time.time()
        try:
            resp = client.get("/api/analytics/funnel", headers=headers)
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            _print_result("GET /api/analytics/funnel", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("GET /api/analytics/funnel", False, elapsed, str(e))
            results.append(False)

        # 8. Billing plans
        start = time.time()
        try:
            resp = client.get("/api/billing/plans", headers=headers)
            elapsed = (time.time() - start) * 1000
            passed = resp.status_code == 200
            _print_result("GET /api/billing/plans", passed, elapsed)
            results.append(passed)
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            _print_result("GET /api/billing/plans", False, elapsed, str(e))
            results.append(False)

    # Summary
    total = len(results)
    passed_count = sum(results)
    print(f"\n{'='*50}")
    print(f"Results: {passed_count}/{total} passed")

    return all(results)


if __name__ == "__main__":
    success = run_smoke_tests()
    sys.exit(0 if success else 1)
