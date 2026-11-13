import os
import ssl
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, MetaData, String, Table, create_engine, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
metadata = MetaData()
users = Table("users", metadata,
    Column("id", String(36), primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("password_hash", String(200), nullable=False), mysql_engine="InnoDB")
sessions = Table("sessions", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id"), nullable=False),
    Column("expires", Float(precision=53), nullable=False, index=True), mysql_engine="InnoDB")
funds = Table("funds", metadata,
    Column("user_id", String(36), ForeignKey("users.id"), primary_key=True),
    Column("state", JSON, nullable=False), mysql_engine="InnoDB")
login_attempts = Table("login_attempts", metadata,
    Column("key", String(64), primary_key=True),
    Column("attempts", Integer, nullable=False),
    Column("since", Float(precision=53), nullable=False, index=True), mysql_engine="InnoDB")


def empty_state():
    return {"loans": [], "members": [], "contributions": []}


@lru_cache(maxsize=8)
def _engine(url, tls, ca):
    parsed = make_url(url)
    if parsed.drivername == "sqlite":
        # SQLite is used only for isolated tests, never as an implicit fallback.
        if os.environ.get("ALLOW_SQLITE_TESTS") != "1":
            raise RuntimeError("Configure DATABASE_URL for MySQL; SQLite is only supported by the test suite.")
        return create_engine(parsed, connect_args={"check_same_thread": False})
    if parsed.drivername not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError("DATABASE_URL must use mysql+pymysql://")
    parsed = parsed.set(drivername="mysql+pymysql", query={**parsed.query, "charset": "utf8mb4"})
    options = {"connect_timeout": 10, "read_timeout": 20, "write_timeout": 20}
    if tls:
        options["ssl"] = ssl.create_default_context(cafile=ca or None)
    # No idle connection pools per serverless instance; each transaction closes its connection.
    return create_engine(parsed, connect_args=options, poolclass=NullPool, hide_parameters=True)


def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is missing. Copy .env.example to .env and configure MySQL.")
    return _engine(url, os.environ.get("DATABASE_SSL", "true").lower() == "true", os.environ.get("DATABASE_SSL_CA", ""))


def init_database():
    metadata.create_all(get_engine())


@contextmanager
def database():
    with get_engine().connect() as connection:
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def load_state(connection, user_id, lock=False):
    if lock:
        # Lock the account even before its first fund row exists.
        connection.execute(select(users.c.id).where(users.c.id == user_id).with_for_update()).first()
    row = connection.execute(select(funds.c.state).where(funds.c.user_id == user_id)).first()
    return row.state if row else empty_state()


def save_state(connection, user_id, state):
    existing = connection.execute(select(funds.c.user_id).where(funds.c.user_id == user_id)).first()
    if existing:
        connection.execute(update(funds).where(funds.c.user_id == user_id).values(state=state))
    else:
        connection.execute(funds.insert().values(user_id=user_id, state=state))


def ensure_login_attempt(connection, key, now):
    values = {"key": key, "attempts": 0, "since": now}
    if connection.dialect.name == "mysql":
        statement = mysql_insert(login_attempts).values(**values).on_duplicate_key_update(key=key)
    else:
        statement = sqlite_insert(login_attempts).values(**values).on_conflict_do_nothing(index_elements=["key"])
    connection.execute(statement)
    return connection.execute(select(login_attempts).where(login_attempts.c.key == key).with_for_update()).mappings().one()
