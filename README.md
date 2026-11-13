# KshemaNidhi backend

Python FastAPI API backed by hosted PostgreSQL (Neon) or MySQL (including TiDB Cloud). Frontend repository: https://github.com/ashwin-dev0/KshemaNidhi

## Setup (from this repository root)

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your real DATABASE_URL. URL-encode special characters in the username/password. The database must already exist; initialization creates its tables. Use a postgresql:// connection URL for Neon or mysql+pymysql:// for MySQL. Keep DATABASE_SSL=true for hosted databases; TLS verifies the certificate and hostname. DATABASE_SSL_CA is optional for providers requiring a custom CA file. For local MySQL without TLS only, set DATABASE_SSL=false.

```powershell
.venv/Scripts/python.exe -m backend.init_db
.venv/Scripts/python.exe -m backend.create_user your-email@example.com
.venv/Scripts/python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

The create-user command prompts for a password. Every account owns its own fund records. There is no default login or public registration. API documentation: http://127.0.0.1:8000/docs

## Import existing records

If importing your old account, skip create_user and run:

```powershell
.venv/Scripts/python.exe -m backend.migrate_sqlite C:/path/to/fund.sqlite3
```

Stop the old API while importing. The importer leaves the source unchanged and preserves accounts/password hashes, inactive members, loans, repayments, and contributions. Conflicting target records abort the transaction. Sign in again after import; old sessions are not copied. Never commit the SQLite file or database exports.

## Tests

```powershell
.venv/Scripts/python.exe -m unittest backend.test_api backend.test_database -v
```

These use isolated SQLite fixtures and MySQL SQL-generation checks. For real MySQL integration tests, set TEST_MYSQL_URL to an EMPTY disposable database ending in `_test`, then run `python -m unittest backend.test_mysql -v`. Test tables are created and removed; do not use a production database.

## Deployment

For Vercel, import this repository as a FastAPI backend. `app.py` exports the ASGI application and root `requirements.txt` installs dependencies. Set DATABASE_URL, DATABASE_SSL=true, COOKIE_SECURE=true, and ALLOWED_ORIGINS to the exact frontend origin. Keep the repository root as the project root. Initialize the remote database and create/import your account once from a local terminal using that database connection; tables are not created inside each request.

For a Python web service, install with `pip install -r requirements.txt` and start with `uvicorn app:app --host 0.0.0.0 --port $PORT`. The hosted database persists records independently of the web service. Configure backups with your database provider.

The frontend must proxy `/api/*` to this service under its own origin. Database credentials belong only on the backend. No database files, passwords, environment files, or virtual environment are committed.

## API

- POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout
- GET /api/fund, DELETE /api/fund (reset signed-in account)
- POST /api/members, DELETE /api/members/{id} (soft delete)
- POST /api/loans, DELETE /api/loans/{id}
- PUT /api/loans/{id}/payments/{number} with {"paid": true}
- PUT /api/contributions with {"memberIds": ["id"], "month": "2026-11", "received": true}
- GET /api/health

Fund mutations use transactions and account row locks. Passwords are salted PBKDF2-SHA256 hashes. Sessions use HttpOnly cookies; logout revokes the server session. Opening fund is not part of the API. Each fund is a JSON document in the database, intended for small family funds.

## Hosted Postgres verification

The production deployment uses the free Neon database connected through Vercel Marketplace. Keep DATABASE_URL only on the backend. After provisioning, run backend.init_db once with the production environment loaded, then create the login using backend.create_user.

Set RUN_POSTGRES_TESTS=1 with DATABASE_URL configured to run python -m unittest backend.test_postgres -v. These opt-in tests create unique verification schemas and remove them after each test; application records are unchanged.
