"""Opt-in integration tests. TEST_MYSQL_URL must name an EMPTY database ending in _test."""
import os
import unittest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from . import test_api
from .main import app
from .database import database, get_engine, init_database, metadata, users
from .security import hash_password


@unittest.skipUnless(os.environ.get("TEST_MYSQL_URL"), "Set TEST_MYSQL_URL to an empty disposable MySQL database ending in _test")
class MySQLApiTests(test_api.ApiTests):
    def setUp(self):
        url = os.environ["TEST_MYSQL_URL"]
        parsed = make_url(url)
        if parsed.get_backend_name() != "mysql" or not (parsed.database or "").endswith("_test"):
            raise RuntimeError("TEST_MYSQL_URL must point to a disposable MySQL database ending in _test")
        self.old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        self.addCleanup(self.restore_url)
        engine = get_engine()
        if inspect(engine).get_table_names():
            raise RuntimeError("Test database must be empty; refusing to overwrite existing tables")
        init_database()
        self.addCleanup(lambda: metadata.drop_all(engine))
        with database() as connection:
            for email in ("admin@example.com", "other@example.com"):
                connection.execute(users.insert().values(id=str(uuid.uuid4()), email=email, password_hash=hash_password("test-password")))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def tearDown(self):
        pass

    def restore_url(self):
        get_engine().dispose()
        if self.old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.old_url
