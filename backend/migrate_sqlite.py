"""Copy legacy SQLite accounts and fund history into the configured MySQL database."""
import argparse
import json
import sqlite3
from pathlib import Path
from sqlalchemy import select
from .database import database, init_database, users, funds, save_state


def migrate(source_path):
    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        raise ValueError("Source SQLite file does not exist")
    # Read-only connection; the original database is never changed.
    source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        source.execute("BEGIN")
        old_users = [dict(row) for row in source.execute("SELECT id, email, password_hash FROM users")]
        old_funds = [dict(row) for row in source.execute("SELECT user_id, state FROM funds")]
    finally:
        source.close()
    init_database()
    with database() as target:
        for user in old_users:
            existing = target.execute(select(users).where((users.c.id == user["id"]) | (users.c.email == user["email"])).with_for_update()).mappings().first()
            if existing:
                if dict(existing) != user:
                    raise ValueError("An account conflicts with the source. No records were imported; use an empty destination database.")
            else:
                target.execute(users.insert().values(**user))
        for fund in old_funds:
            payload = json.loads(fund["state"])
            state = {key: payload.get(key, []) for key in ("loans", "members", "contributions")}
            if not all(isinstance(value, list) for value in state.values()):
                raise ValueError("Invalid source fund data; no records were imported")
            existing = target.execute(select(funds.c.state).where(funds.c.user_id == fund["user_id"]).with_for_update()).first()
            if existing and existing.state != state:
                raise ValueError("Destination fund already has different records. No records were imported.")
            if not existing:
                save_state(target, fund["user_id"], state)
    return len(old_users), len(old_funds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=str(Path(__file__).parent / "data" / "fund.sqlite3"))
    args = parser.parse_args()
    accounts, records = migrate(args.source)
    print(f"Migration complete: {accounts} accounts and {records} funds verified/imported. Sign in again to create a new session.")


if __name__ == "__main__":
    main()
