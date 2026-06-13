# Deployment Guide

This document describes how to deploy OpenQMS, including Docker Compose (recommended) and local development environment setups.

---

## 1. Docker Compose Deployment (Recommended)

### 1.1 Prerequisites

| Dependency | Minimum Version | Description |
|------------|-----------------|-------------|
| Docker | 20.10+ | Container runtime |
| Docker Compose | v2.0+ | Service orchestration |
| Available memory | 4 GB+ | PostgreSQL + Neo4j + Ollama each need 256–512 MB |

### 1.2 Configuration

The project root provides `.env.example`. Copy and modify it for production:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://qms:qms_dev_2026@db:5432/qms` | Database connection (inside Docker) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `SECRET_KEY` | `openqms-local-dev-2026-jwt-signing-key` | **JWT signing key — must be changed in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | Token expiration time (minutes) |

> ⚠️ `SECRET_KEY` must be replaced with a random long string in production, otherwise it poses a security risk.

### 1.3 Start Services

```bash
docker compose up -d
```

The first startup will automatically build frontend and backend images. Check service status:

```bash
docker compose ps
```

Wait for the `db` and `neo4j` containers to become `healthy` (approximately 15–30 seconds).

### 1.4 Initialize the Database

```bash
# Run database migrations
docker compose exec backend alembic upgrade head

# Import demo data (includes users, FMEA, CAPA, suppliers, etc.)
docker compose exec backend python -m app.seed
```

### 1.5 Access

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000/api |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Neo4j Browser | http://localhost:7474 |

### 1.6 Default Accounts

| Username | Password | Role |
|----------|----------|------|
| `admin` | `Admin@2026` | System Administrator |
| `engineer` | `Engineer@2026` | Field Quality Engineer |
| `manager` | `Manager@2026` | Quality Manager |
| `viewer` | `Viewer@2026` | Read-only User |
| `groupadmin` | `GroupAdmin@2026` | Group Administrator |

> ⚠️ Be sure to change default passwords in production.

### 1.7 Stop and Restart

```bash
# Stop all services
docker compose down

# Stop and remove data volumes (reset the database)
docker compose down -v

# Restart a single service
docker compose restart backend
```

---

## 2. Local Development Environment

### 2.1 Prerequisites

| Dependency | Version |
|------------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 15+ |
| Redis | 7+ |

### 2.2 Backend

```bash
cd backend
pip install -r requirements.txt

# Configure environment variables
cp ../.env.example .env
# Edit DATABASE_URL and REDIS_URL in .env to point to local services

# Database migration
alembic upgrade head

# Import demo data
python -m app.seed

# Start development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.3 Frontend

```bash
cd frontend
npm install

# Start development server (auto-proxies /api → localhost:8000)
npm run dev
```

The frontend runs at `http://localhost:5173` by default, with Vite proxying `/api` requests to the backend.

### 2.4 Environment Variables

For local development, the backend reads the `.env` file from the project root or the `backend/` directory:

```env
DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=120
```

---

## 3. Database Migrations

Alembic manages all database schema changes.

```bash
# Apply all pending migrations
alembic upgrade head

# Check current version
alembic current

# View migration history
alembic history

# Roll back one version
alembic downgrade -1
```

> ⚠️ Migration files are hand-written (not auto-generated). Do not use `alembic revision --autogenerate` to overwrite existing migrations.

---

## 4. Common Issues

### 4.1 Database Connection Failure

```
sqlalchemy.exc.OperationalError: connection refused
```

- Check if PostgreSQL is running: `docker compose ps db`
- Check that the hostname in `DATABASE_URL` is correct (`db` inside Docker, `localhost` for local)
- Confirm the `qms` database has been created

### 4.2 Frontend Proxy 404

- Confirm the backend is running at `localhost:8000`
- Check the proxy configuration in `frontend/vite.config.ts`
- In Docker, the frontend uses the `BACKEND_URL` environment variable to point to the backend

### 4.3 Neo4j Connection Failure

- Check if the Neo4j container is `healthy`: `docker compose ps neo4j`
- Knowledge graph features depend on Neo4j; if not needed, you can ignore this error
- Visit `http://localhost:7474` in a browser to verify Neo4j Browser is available

### 4.4 Seed Data Error "Already seeded"

This means the database already has seed data — you can skip this. If you need to reset:

```bash
docker compose down -v    # Remove data volumes
docker compose up -d      # Restart
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

### 4.5 Ollama Out of Memory

The Ollama container has a default memory limit of 2 GB. To run larger models, adjust the `memory` limit for the `ollama` service in `docker-compose.yml`, or disable AI recommendation features.