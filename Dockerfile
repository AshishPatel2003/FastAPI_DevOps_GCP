# Stage 1: Build dependencies
FROM python:3.14.4-slim AS builder

# Set env variables to not write pyc files and not buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies needed for some python packages (e.g., psycopg2, asyncpg, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements to cache them in docker layer
COPY requirements.txt .

# Create a virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Stage 2: Runner
FROM python:3.14.4-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Run as non-root user
RUN groupadd -g 1001 fastapi && \
    useradd -r -u 1001 -g fastapi fastapi

WORKDIR /app

# Install runtime system dependencies if needed (libpq5 for postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder stage
COPY --from=builder --chown=fastapi:fastapi /opt/venv /opt/venv

# Copy application code
COPY --chown=fastapi:fastapi app/ app/
COPY --chown=fastapi:fastapi alembic/ alembic/
COPY --chown=fastapi:fastapi alembic.ini .

# Pre-compile python files for faster startup
RUN python -m compileall app/

# Switch to non-root user
USER fastapi

EXPOSE 8080

# Command to run the application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
