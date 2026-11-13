"""Opt-in hosted Postgres verification in a unique schema, isolated from app records."""
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateSchema, DropSchema

from . import test_api
from .database import get_engine, metadata, users
from .main import app
from .security import hash_password


@unittest.skipUnless(os.environ.get("RUN_POSTGRES_TESTS") == "1", "Opt-in hosted Postgres tests")
class PostgresApiTests(test_api.ApiTests):
    def setUp(self):
        base = get_engine()
        if base.dialect.name != "postgresql":
            raise RuntimeError("Postgres verification requires a Postgres connection")
        schema = "verification_" + uuid.uuid4().hex
        with base.begin() as connection:
            connection.execute(CreateSchema(schema))

        def cleanup_schema():
            with base.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))

        self.addCleanup(cleanup_schema)
        engine = base.execution_options(schema_translate_map={None: schema})
        self.engine_patch = patch("backend.database.get_engine", return_value=engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        metadata.create_all(engine)
        with engine.begin() as connection:
            for email in ("admin@example.com", "other@example.com"):
                connection.execute(users.insert().values(id=str(uuid.uuid4()), email=email, password_hash=hash_password("test-password")))
        self.client = TestClient(app, base_url="https://testserver")
        self.addCleanup(self.client.close)

    def tearDown(self):
        pass
