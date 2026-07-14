import unittest
from fastapi.testclient import TestClient
import os

# Set environment variables for testing
os.environ["MT5_MOCK_MODE"] = "True"
os.environ["API_KEY"] = "test-api-key"
os.environ["ENCRYPTION_KEY"] = "U3VwZXJTZWNyZXRLZXlGb3JUZXN0aW5nMTIzNDU2Nzg="
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.main import app
from app.database import init_db

class TestExnessServiceAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize test database
        init_db()
        cls.client = TestClient(app)
        cls.headers = {"X-API-Key": "test-api-key"}

    @classmethod
    def tearDownClass(cls):
        # Remove test database file
        if os.path.exists("test.db"):
            try:
                os.remove("test.db")
            except Exception:
                pass

    def test_unauthorized_access(self):
        """Verify that requests without correct API keys are rejected."""
        # Missing header returns 422 Unprocessable Entity because X-API-Key is required
        response = self.client.get("/api/v1/accounts/user_123/balance")
        self.assertEqual(response.status_code, 422)
        
        # Wrong key returns 401 Unauthorized
        response = self.client.get("/api/v1/accounts/user_123/balance", headers={"X-API-Key": "wrong-key"})
        self.assertEqual(response.status_code, 401)

    def test_account_registration_and_balance(self):
        """Verify account registration, validation, and balance fetch."""
        # 1. Register account
        reg_payload = {
            "user_id": "test_user_1",
            "login": 987654,
            "password": "mysecretpassword123",
            "server": "Exness-MT5Real1"
        }
        response = self.client.post(
            "/api/v1/accounts/register",
            json=reg_payload,
            headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

        # 2. Login verification
        login_payload = {
            "user_id": "test_user_1",
            "login": 987654,
            "password": "mysecretpassword123",
            "server": "Exness-MT5Real1"
        }
        response = self.client.post(
            "/api/v1/accounts/login",
            json=login_payload,
            headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["authenticated"])

        # 3. Retrieve balance
        response = self.client.get(
            "/api/v1/accounts/test_user_1/balance",
            headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("balance", data)
        self.assertEqual(data["balance"], 10000.0)

if __name__ == "__main__":
    unittest.main()
