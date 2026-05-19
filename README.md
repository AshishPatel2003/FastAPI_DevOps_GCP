# FastAPI DevOps GCP

Enterprise-grade FastAPI project with full CI/CD, PostgreSQL, Redis WebSocket Pub/Sub, and GCP Cloud Run deployment.

## Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- PostgreSQL
- Redis

### Setup

1. Copy environment variables:
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` to match your local database and Redis credentials.*

2. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

3. Run database migrations:
   ```bash
   alembic upgrade head
   ```

4. Start the development server:
   ```bash
   uvicorn app.main:app --reload --port 8080
   ```

## Documentation

Full documentation is available in the `docs/` directory:

- **Deployment & Infrastructure:**
  - [Deployment Guide](docs/deployment/DEPLOYMENT.md)
  - [Load Balancer & Custom Domain](docs/deployment/LOAD_BALANCER.md)
  - [Environment Variables Setup](docs/deployment/ENVIRONMENT_SETUP.md)

- **Database:**
  - [PostgreSQL Setup (Primary)](docs/database/DATABASE_POSTGRESQL.md)
  - [MySQL Reference](docs/database/DATABASE_MYSQL.md)
  - [MongoDB Reference](docs/database/DATABASE_MONGODB.md)
  - [Firestore Reference](docs/database/DATABASE_FIRESTORE.md)

- **Services:**
  - [GCP Storage Setup](docs/storage/GCS_STORAGE.md)
  - [Redis Cloud Setup](docs/cache/REDIS_SETUP.md)
  - [GCP Cloud Logging](docs/logging/GCP_LOGGING.md)

## Architecture

This project is configured to automatically deploy to Google Cloud Run across 3 environments:
- `develop` branch -> `development` environment
- `stage` branch -> `staging` environment
- `main` branch -> `production` environment

See [Deployment Guide](docs/deployment/DEPLOYMENT.md) for details.
