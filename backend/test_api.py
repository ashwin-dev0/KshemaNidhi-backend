import os
import tempfile
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from .main import app
from .database import database, init_database, users, get_engine
from .security import hash_password


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = os.environ.get("DATABASE_URL")
        self.old_test = os.environ.get("ALLOW_SQLITE_TESTS")
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(self.temp.name) / "test.sqlite3").as_posix()
        os.environ["ALLOW_SQLITE_TESTS"] = "1"
        init_database()
        with database() as connection:
            for email in ("admin@example.com", "other@example.com"):
                connection.execute(users.insert().values(id=str(uuid.uuid4()), email=email, password_hash=hash_password("test-password")))
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        get_engine().dispose()
        if self.old_test is None:
            os.environ.pop("ALLOW_SQLITE_TESTS", None)
        else:
            os.environ["ALLOW_SQLITE_TESTS"] = self.old_test
        if self.old_path is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.old_path
        self.temp.cleanup()

    def login(self, client=None, email="admin@example.com"):
        response = (client or self.client).post("/api/auth/login", json={"email": email, "password": "test-password"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])

    def test_authentication_and_revocation(self):
        self.assertEqual(self.client.get("/api/fund").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong-password"}).status_code, 401)
        self.login()
        token = self.client.cookies.get("kshemanidhi_session")
        self.assertEqual(self.client.get("/api/auth/me").json()["email"], "admin@example.com")
        self.client.post("/api/auth/logout")
        self.client.cookies.set("kshemanidhi_session", token)
        self.assertEqual(self.client.get("/api/fund").status_code, 401)

    def test_fund_workflow_persistence_and_isolation(self):
        self.login()
        response = self.client.post("/api/members", json={"name": " Family member "})
        self.assertEqual(response.status_code, 200, response.text)
        member = response.json()["members"][0]
        self.assertEqual(member["name"], "Family member")
        contribution = {"memberIds": [member["id"]], "month": "2026-11", "received": True}
        self.client.put("/api/contributions", json=contribution)
        state = self.client.put("/api/contributions", json=contribution).json()
        self.assertEqual(len(state["contributions"]), 1)
        self.assertEqual(state["contributions"][0]["amount"], 1000)
        payload = {"memberId": member["id"], "date": "2026-01-31", "principal": 1000, "installments": 3, "method": "REDUCING"}
        result = self.client.post("/api/loans", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        loan = result.json()["loans"][0]
        self.assertEqual(loan["schedule"][0]["dueDate"], "2026-02-28")
        self.assertEqual(sum(row["principalDue"] for row in loan["schedule"]), 1000)
        self.assertEqual(loan["schedule"][-1]["amountDue"], 20)
        path = f'/api/loans/{loan["id"]}/payments/1'
        self.client.put(path, json={"paid": True})
        state = self.client.put(path, json={"paid": True}).json()
        self.assertTrue(state["loans"][0]["schedule"][0]["paid"])
        self.assertNotIn("openingFund", state)
        with TestClient(app) as fresh:
            self.login(fresh)
            self.assertEqual(fresh.get("/api/fund").json(), state)
        with TestClient(app) as other:
            self.login(other, "other@example.com")
            self.assertEqual(other.get("/api/fund").json()["members"], [])
            self.assertEqual(other.put(path, json={"paid": True}).status_code, 404)
            other.delete("/api/fund")
        self.assertEqual(len(self.client.get("/api/fund").json()["loans"]), 1)
        self.client.delete(f'/api/members/{member["id"]}')
        self.assertEqual(self.client.post("/api/loans", json=payload).status_code, 400)
        self.client.delete(f'/api/loans/{loan["id"]}')
        self.assertEqual(self.client.get("/api/fund").json()["loans"], [])
        self.assertEqual(self.client.delete("/api/fund").json(), {"loans": [], "members": [], "contributions": []})

    def test_validation_origin_and_atomic_updates(self):
        self.login()
        self.assertEqual(self.client.post("/api/members", json={"name": " "}).status_code, 422)
        self.assertEqual(self.client.post("/api/members", json={"name": "X"}, headers={"Origin": "https://untrusted.example"}).status_code, 403)
        member = self.client.post("/api/members", json={"name": "A"}).json()["members"][0]
        self.assertEqual(self.client.put("/api/contributions", json={"memberIds": [member["id"]], "month": "2026-13", "received": True}).status_code, 422)
        self.assertEqual(self.client.put("/api/contributions", json={"memberIds": [member["id"], "missing"], "month": "2026-11", "received": True}).status_code, 404)
        self.assertEqual(self.client.get("/api/fund").json()["contributions"], [])
        for value in (-1, 0, 0.001):
            self.assertEqual(self.client.post("/api/loans", json={"memberId": member["id"], "date": "2026-11-01", "principal": value, "installments": 3, "method": "SIMPLE"}).status_code, 422)
        response = self.client.post("/api/loans", json={"memberId": member["id"], "date": "2026-11-01", "principal": 1000, "installments": 3, "method": "SIMPLE"})
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()["loans"][0]["schedule"]
        self.assertEqual([row["amountDue"] for row in rows], [10, 10, 10, 1000])

    def test_login_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong-password"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "admin@example.com", "password": "test-password"}).status_code, 429)


if __name__ == "__main__":
    unittest.main()
