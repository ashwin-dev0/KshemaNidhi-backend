from contextlib import closing
import ssl
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable
from .database import _engine, metadata, users, database, init_database, get_engine, load_state
from .migrate_sqlite import migrate


class DatabaseTests(unittest.TestCase):
    def test_mysql_schema_and_lock_sql(self):
        ddl = "\n".join(str(CreateTable(table).compile(dialect=mysql.dialect())) for table in metadata.sorted_tables)
        self.assertIn("state JSON NOT NULL", ddl)
        self.assertIn("ENGINE=InnoDB", ddl)
        self.assertIn("VARCHAR(254)", ddl)
        statement = str(select(users.c.id).where(users.c.id == "id").with_for_update().compile(dialect=mysql.dialect()))
        self.assertIn("FOR UPDATE", statement)
        self.assertNotIn("BEGIN IMMEDIATE", statement)

    def test_mysql_configuration_and_verified_tls(self):
        with patch.dict(os.environ, {"DATABASE_URL": "mysql+pymysql://user:password@localhost/fund", "DATABASE_SSL": "true"}):
            engine = get_engine()
            self.assertEqual(engine.dialect.name, "mysql")
            self.assertEqual(engine.url.query["charset"], "utf8mb4")
            self.assertNotIn("password", str(engine.url))
            engine.dispose()
        with patch("backend.database.create_engine") as create:
            _engine("mysql+pymysql://tls-check:password@localhost/fund", True, "")
            context = create.call_args.kwargs["connect_args"]["ssl"]
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is missing"):
                get_engine()

    def test_readonly_migration_preserves_history_and_rejects_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.sqlite3"
            state = {"members": [{"id": "member", "name": "Archived", "active": False}], "loans": [{"id": "loan", "schedule": [{"paid": True}]}], "contributions": [{"id": "contribution", "received": True}]}
            with closing(sqlite3.connect(source_path)) as source:
                source.execute("CREATE TABLE users (id TEXT, email TEXT, password_hash TEXT)")
                source.execute("CREATE TABLE funds (user_id TEXT, state TEXT)")
                source.execute("INSERT INTO users VALUES ('account', 'old@example.com', 'existing-hash')")
                source.execute("INSERT INTO funds VALUES (?, ?)", ("account", json.dumps(state)))
                source.commit()
            before = source_path.read_bytes()
            target = Path(directory) / "target.sqlite3"
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///" + target.as_posix(), "ALLOW_SQLITE_TESTS": "1"}):
                init_database()
                self.assertEqual(migrate(source_path), (1, 1))
                self.assertEqual(source_path.read_bytes(), before)
                self.assertEqual(migrate(source_path), (1, 1))
                with database() as connection:
                    self.assertEqual(load_state(connection, "account"), state)
                    self.assertEqual(connection.execute(select(users.c.password_hash)).scalar_one(), "existing-hash")
                with closing(sqlite3.connect(source_path)) as source:
                    source.execute("UPDATE users SET password_hash = 'conflicting-hash'")
                    source.commit()
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    migrate(source_path)
                with database() as connection:
                    self.assertEqual(connection.execute(select(users.c.password_hash)).scalar_one(), "existing-hash")
                get_engine().dispose()
