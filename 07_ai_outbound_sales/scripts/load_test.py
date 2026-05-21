"""Load test script using Locust for the AI Outbound Sales platform.

Usage:
    locust -f scripts/load_test.py --host http://localhost:8000

User scenarios:
- LoginUser: Authenticates then browses dashboard endpoints
- LeadCreator: Creates leads at a moderate rate
- BillingChecker: Checks plans and usage endpoints
"""

import uuid

from locust import HttpUser, TaskSet, between, task


class LoginUserTasks(TaskSet):
    """Simulates a user logging in and browsing the dashboard."""

    token = None

    def on_start(self):
        """Register and login to get a token."""
        email = f"load-{uuid.uuid4().hex[:8]}@loadtest.com"
        password = "loadtest_pass_123"

        self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": password,
                "tenant_name": "Load Test Corp",
            },
        )

        resp = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    @property
    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(3)
    def list_campaigns(self):
        self.client.get("/api/campaigns/", headers=self._headers)

    @task(2)
    def list_leads(self):
        self.client.get("/api/leads/", headers=self._headers)

    @task(2)
    def get_analytics_funnel(self):
        self.client.get("/api/analytics/funnel", headers=self._headers)

    @task(1)
    def get_voice_stats(self):
        self.client.get("/api/voice/stats", headers=self._headers)

    @task(1)
    def get_me(self):
        self.client.get("/api/auth/me", headers=self._headers)


class LeadCreatorTasks(TaskSet):
    """Simulates a user creating leads."""

    token = None

    def on_start(self):
        """Register and login to get a token."""
        email = f"lead-creator-{uuid.uuid4().hex[:8]}@loadtest.com"
        password = "loadtest_pass_123"

        self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": password,
                "tenant_name": "Lead Creator Corp",
            },
        )

        resp = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    @property
    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task
    def create_lead(self):
        self.client.post(
            "/api/leads/",
            json={
                "email": f"lead-{uuid.uuid4().hex[:8]}@example.com",
                "first_name": "Load",
                "last_name": "Test",
                "company": "Load Test Inc",
                "title": "Engineer",
            },
            headers=self._headers,
        )


class BillingCheckerTasks(TaskSet):
    """Simulates a user checking billing information."""

    token = None

    def on_start(self):
        """Register and login to get a token."""
        email = f"billing-{uuid.uuid4().hex[:8]}@loadtest.com"
        password = "loadtest_pass_123"

        self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": password,
                "tenant_name": "Billing Checker Corp",
            },
        )

        resp = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    @property
    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(3)
    def get_plans(self):
        self.client.get("/api/billing/plans", headers=self._headers)

    @task(2)
    def get_usage(self):
        self.client.get("/api/billing/usage", headers=self._headers)

    @task(1)
    def get_subscription(self):
        self.client.get("/api/billing/subscription", headers=self._headers)


class LoginUser(HttpUser):
    """User that logs in and browses the dashboard."""

    tasks = [LoginUserTasks]
    wait_time = between(1, 5)
    weight = 5


class LeadCreator(HttpUser):
    """User that creates leads."""

    tasks = [LeadCreatorTasks]
    wait_time = between(2, 8)
    weight = 3


class BillingChecker(HttpUser):
    """User that checks billing info."""

    tasks = [BillingCheckerTasks]
    wait_time = between(3, 10)
    weight = 2
