# PostgreSQL on Cloud SQL

## Setup
1. Run `scripts/database/setup-cloudsql.sh`
2. It provisions the instance, database, and user.
3. Add the generated `CLOUD_SQL_INSTANCE` to GitHub Variables.
4. Add the generated `DATABASE_URL` to GitHub Secrets.

## Cloud Run Connection (Unix Sockets)
The application automatically detects if `CLOUD_SQL_INSTANCE` is set and connects via the Unix Socket injected by the Cloud Run Cloud SQL Auth Proxy (`/cloudsql/PROJ:REGION:INSTANCE`).

## Migrations
Alembic is configured to run async migrations. For local dev:
```bash
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```
