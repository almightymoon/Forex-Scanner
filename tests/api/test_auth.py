"""Authentication and protected route tests."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

os.environ.setdefault("ENABLE_SIMULATED_DATA", "true")
os.environ.setdefault("MARKET_DATA_PROVIDER", "simulated")

from apps.api.auth import hash_password, verify_password, _users_db  # noqa: E402
from apps.api.main import app  # noqa: E402


class TestPasswordHashing(unittest.TestCase):
    def test_bcrypt_hash_and_verify(self):
        hashed = hash_password("secure-password")
        self.assertNotEqual(hashed, "secure-password")
        self.assertTrue(verify_password("secure-password", hashed))
        self.assertFalse(verify_password("wrong", hashed))


class TestJWTAuth(unittest.TestCase):
    def setUp(self):
        _users_db.clear()
        self.client = TestClient(app)

    def test_register_and_login(self):
        res = self.client.post(
            "/api/v1/auth/register",
            json={"name": "Test", "email": "test@example.com", "password": "secret123"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access_token", res.json())
        self.assertIn("refresh_token", res.json())

        user = _users_db["test@example.com"]
        self.assertIn("password_hash", user)
        self.assertNotEqual(user["password_hash"], "secret123")

    def test_login_invalid_credentials(self):
        self.client.post(
            "/api/v1/auth/register",
            json={"name": "Test", "email": "test@example.com", "password": "secret123"},
        )
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "wrong"},
        )
        self.assertEqual(res.status_code, 401)

    def test_protected_dashboard_requires_auth(self):
        res = self.client.get("/api/v1/dashboard")
        self.assertEqual(res.status_code, 401)

    def test_protected_watchlist_with_token(self):
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"name": "Test", "email": "user@example.com", "password": "secret123"},
        )
        token = reg.json()["access_token"]
        res = self.client.get(
            "/api/v1/watchlist",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("symbols", res.json())


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_returns_provider_fields(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("provider", data)
        self.assertIn("provider_status", data)
        self.assertIn("simulated", data)
        self.assertIn("status", data)


if __name__ == "__main__":
    unittest.main()
