"""Foundation sprint — explicit simulation, billing identity, strategy ownership."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

os.environ["ENABLE_SIMULATED_DATA"] = "true"
os.environ["MARKET_DATA_PROVIDER"] = "simulated"

from apps.api.auth import _users_db  # noqa: E402
from apps.api.main import app  # noqa: E402
from shared.config.market import get_market_config, is_simulated_mode, reload_market_config


class TestExplicitSimulation(unittest.TestCase):
    def tearDown(self):
        reload_market_config()

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "false", "ENVIRONMENT": "development"}, clear=False)
    def test_environment_does_not_enable_simulation(self):
        reload_market_config()
        self.assertFalse(is_simulated_mode())

    @patch.dict(os.environ, {"ENABLE_SIMULATED_DATA": "true"}, clear=False)
    def test_explicit_env_enables_simulation(self):
        reload_market_config()
        self.assertTrue(is_simulated_mode())


class TestBillingIdentity(unittest.TestCase):
    def setUp(self):
        _users_db.clear()
        self.client = TestClient(app)
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"name": "Trader", "email": "trader@example.com", "password": "secret123"},
        )
        self.token = reg.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @patch("services.billing_service.stripe_billing.BillingService.create_checkout_session")
    def test_checkout_uses_jwt_email_not_body(self, mock_checkout):
        mock_checkout.return_value = {"url": "https://checkout.stripe.com/test"}
        res = self.client.post(
            "/api/v1/billing/checkout",
            json={"plan_id": "pro"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        mock_checkout.assert_called_once()
        self.assertEqual(mock_checkout.call_args.kwargs["user_email"], "trader@example.com")

    def test_checkout_requires_auth(self):
        res = self.client.post("/api/v1/billing/checkout", json={"plan_id": "pro"})
        self.assertEqual(res.status_code, 401)


class TestStrategyOwnership(unittest.TestCase):
    def setUp(self):
        _users_db.clear()
        self.client = TestClient(app)

    def _auth_headers(self, email: str) -> dict:
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"name": "User", "email": email, "password": "secret123"},
        )
        token = reg.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_strategies_require_auth(self):
        res = self.client.get("/api/v1/strategies")
        self.assertEqual(res.status_code, 401)

    def test_cannot_delete_other_users_strategy(self):
        headers_a = self._auth_headers("alice@example.com")
        headers_b = self._auth_headers("bob@example.com")

        created = self.client.post(
            "/api/v1/strategies",
            json={
                "name": "Alice Strategy",
                "rules": [{"field": "rsi", "operator": "gt", "value": 50, "label": "RSI"}],
                "combinator": "AND",
                "action": "buy",
                "symbols": [],
                "min_score": 0,
            },
            headers=headers_a,
        )
        self.assertEqual(created.status_code, 200)
        strategy_id = created.json()["id"]

        forbidden = self.client.delete(f"/api/v1/strategies/{strategy_id}", headers=headers_b)
        self.assertEqual(forbidden.status_code, 403)

    def test_cannot_delete_system_strategy(self):
        headers = self._auth_headers("user@example.com")
        res = self.client.delete("/api/v1/strategies/trend-momentum", headers=headers)
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
