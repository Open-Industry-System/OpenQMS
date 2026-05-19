# QMS MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the QMS MVP — a quality management platform with user auth, PFMEA editor, 8D/CAPA workflow, and dashboard, running on Docker Compose.

**Architecture:** React 18 + Vite + Ant Design 5 frontend, FastAPI backend, PostgreSQL 15 with JSONB graph storage, Redis for caching. Monolithic API with clear service boundaries. State machines ported from prototype models.py.

**Tech Stack:** React 18, Vite, TypeScript, Ant Design 5, Zustand, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, PostgreSQL 15, Redis 7, Docker Compose

---

## Phase 1: Project Scaffold & Infrastructure

### Task 1: Docker Compose & Project Root

**Files:**
- Create: `docker-compose.yml`
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
version: "3.8"

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: qms
      POSTGRES_PASSWORD: qms_dev_2026
      POSTGRES_DB: qms
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qms"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    environment:
      DATABASE_URL: postgresql+asyncpg://qms:qms_dev_2026@db:5432/qms
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: dev-secret-key-change-in-production
      ACCESS_TOKEN_EXPIRE_MINUTES: "120"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  frontend:
    build: ./frontend
    command: npm run dev -- --host 0.0.0.0
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      VITE_API_BASE_URL: http://localhost:8000/api
    depends_on:
      - backend

volumes:
  pgdata:
```

- [ ] **Step 2: Write .gitignore**

```
node_modules/
dist/
__pycache__/
*.pyc
.env
.venv/
*.egg-info/
pgdata/
.DS_Store
```

- [ ] **Step 3: Write .env.example**

```
DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=120
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .gitignore .env.example
git commit -m "feat: add Docker Compose scaffold and project root files"
```

---

### Task 2: Backend Scaffold (FastAPI)

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/Dockerfile`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`

- [ ] **Step 1: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.2
pydantic[email]==2.9.2
pydantic-settings==2.5.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.12
redis==5.1.1
httpx==0.27.2
```

- [ ] **Step 2: Write backend/Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Write backend/app/__init__.py**

```python
```

- [ ] **Step 4: Write backend/app/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    ALGORITHM: str = "HS256"

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 5: Write backend/app/database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
```

- [ ] **Step 6: Write backend/app/main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="OpenQMS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Verify the backend starts**

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000 &
sleep 2 && curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
kill %1
```

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: scaffold FastAPI backend with config and database setup"
```

---

### Task 3: Frontend Scaffold (React + Vite + Ant Design)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/Dockerfile`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/vite-env.d.ts`

- [ ] **Step 1: Write frontend/package.json**

```json
{
  "name": "openqms-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint ."
  },
  "dependencies": {
    "antd": "^5.21.0",
    "@ant-design/icons": "^5.4.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
    "axios": "^1.7.7",
    "zustand": "^5.0.0",
    "dayjs": "^1.11.13"
  },
  "devDependencies": {
    "@types/react": "^18.3.8",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.6.2",
    "vite": "^5.4.7"
  }
}
```

- [ ] **Step 2: Write frontend/vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 3: Write frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write frontend/tsconfig.node.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Write frontend/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OpenQMS - 智能质量管理平台</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Write frontend/Dockerfile**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

- [ ] **Step 7: Write frontend/src/vite-env.d.ts**

```typescript
/// <reference types="vite/client" />
```

- [ ] **Step 8: Write frontend/src/main.tsx**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#1677FF" } }}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
);
```

- [ ] **Step 9: Write frontend/src/App.tsx**

```typescript
import { Routes, Route, Navigate } from "react-router-dom";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<div style={{ padding: 48, textAlign: "center" }}>OpenQMS MVP — Coming Soon</div>} />
    </Routes>
  );
}

export default App;
```

- [ ] **Step 10: Verify frontend starts**

```bash
cd frontend && npm install && npm run dev &
sleep 3 && curl http://localhost:5173 | head -5
# Expected: HTML content with OpenQMS title
kill %1
```

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold React frontend with Vite and Ant Design"
```

---

## Phase 2: Backend Core — Auth & Users

### Task 4: User ORM Model & Migration

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_create_users.py`

- [ ] **Step 1: Write backend/app/models/__init__.py**

```python
from app.models.user import User

__all__ = ["User"]
```

- [ ] **Step 2: Write backend/app/models/user.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 3: Write backend/alembic.ini**

```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Write backend/alembic/env.py**

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.database import Base
from app.models import User  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 5: Write backend/alembic/script.py.mako**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Write Alembic migration for users table**

```bash
cd backend && alembic revision --autogenerate -m "create_users"
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ backend/alembic.ini backend/alembic/
git commit -m "feat: add User ORM model and Alembic migration setup"
```

---

### Task 5: Auth Core — JWT & Password Hashing

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/core/deps.py`

- [ ] **Step 1: Write backend/app/core/__init__.py**

```python
```

- [ ] **Step 2: Write backend/app/core/security.py**

```python
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
```

- [ ] **Step 3: Write backend/app/core/deps.py**

```python
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.user_id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/
git commit -m "feat: add JWT auth and RBAC dependency injection"
```

---

### Task 6: Auth API — Login, Register, Me

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/auth.py`

- [ ] **Step 1: Write backend/app/schemas/__init__.py**

```python
```

- [ ] **Step 2: Write backend/app/schemas/auth.py**

```python
import uuid
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: EmailStr | None = None
    role: str = "viewer"


class UserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str | None
    email: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
```

- [ ] **Step 3: Write backend/app/api/__init__.py**

```python
```

- [ ] **Step 4: Write backend/app/api/auth.py**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.user_id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/register", response_model=UserResponse)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username exists")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.username,
        email=req.email,
        role=req.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)
```

- [ ] **Step 5: Register auth routes in main.py**

In `backend/app/main.py`, add after the CORS middleware setup:

```python
from app.api.auth import router as auth_router

app.include_router(auth_router)
```

- [ ] **Step 6: Seed admin user via startup event**

In `backend/app/main.py`, add:

```python
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.database import async_session
from app.models.user import User
from app.core.security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed admin user on startup
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            db.add(User(
                username="admin",
                password_hash=hash_password("Admin@2026"),
                display_name="系统管理员",
                role="admin",
            ))
            await db.commit()
    yield

app = FastAPI(title="OpenQMS API", version="0.1.0", lifespan=lifespan)
```

- [ ] **Step 7: Test auth endpoints**

```bash
cd backend && uvicorn app.main:app --port 8000 &
sleep 2

# Login as admin
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@2026"}' | python3 -m json.tool
# Expected: access_token + user object

# Test /me
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@2026"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Expected: user info

kill %1
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/ backend/app/api/ backend/app/main.py
git commit -m "feat: add auth API endpoints — login, register, me"
```

---

## Phase 3: Backend Core — FMEA & 8D

### Task 7: FMEA & CAPA ORM Models + Migration

**Files:**
- Create: `backend/app/models/fmea.py`
- Create: `backend/app/models/capa.py`
- Create: `backend/app/models/audit.py`

- [ ] **Step 1: Write backend/app/models/fmea.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FMEADocument(Base):
    __tablename__ = "fmea_documents"

    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    fmea_type: Mapped[str] = mapped_column(String(20), default="PFMEA")
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    graph_data: Mapped[dict] = mapped_column(JSONB, default=lambda: {"nodes": [], "edges": []})
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    approver = relationship("User", foreign_keys=[approved_by])
```

- [ ] **Step 2: Write backend/app/models/capa.py**

```python
import uuid
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, DateTime, func, Date, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CAPAEightD(Base):
    __tablename__ = "capa_eightd"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    status: Mapped[str] = mapped_column(String(20), default="D1_TEAM")
    severity: Mapped[str] = mapped_column(String(20), default="一般")
    d1_team: Mapped[dict] = mapped_column(JSONB, default=lambda: [])
    d2_description: Mapped[str | None] = mapped_column(Text)
    d3_interim: Mapped[str | None] = mapped_column(Text)
    d4_root_cause: Mapped[str | None] = mapped_column(Text)
    d5_correction: Mapped[str | None] = mapped_column(Text)
    d6_verification: Mapped[str | None] = mapped_column(Text)
    d7_prevention: Mapped[str | None] = mapped_column(Text)
    d8_closure: Mapped[str | None] = mapped_column(Text)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id")
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 3: Write backend/app/models/audit.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_fields: Mapped[dict | None] = mapped_column(JSONB)
    operated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    operated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Update backend/app/models/__init__.py**

```python
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog

__all__ = ["User", "FMEADocument", "CAPAEightD", "AuditLog"]
```

- [ ] **Step 5: Generate migration and apply**

```bash
cd backend && alembic revision --autogenerate -m "create_fmea_capa_audit"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/fmea.py backend/app/models/capa.py backend/app/models/audit.py backend/app/models/__init__.py backend/alembic/versions/
git commit -m "feat: add FMEA, CAPA, and AuditLog ORM models"
```

---

### Task 8: State Machines (Port from Prototype)

**Files:**
- Create: `backend/app/state_machines/__init__.py`
- Create: `backend/app/state_machines/fmea_state.py`
- Create: `backend/app/state_machines/eightd_state.py`

- [ ] **Step 1: Write backend/app/state_machines/__init__.py**

```python
from app.state_machines.fmea_state import FMEAState, FMEAType, FMEA_TRANSITIONS
from app.state_machines.eightd_state import EightDState, EIGHTD_TRANSITIONS

__all__ = ["FMEAState", "FMEAType", "FMEA_TRANSITIONS", "EightDState", "EIGHTD_TRANSITIONS"]
```

- [ ] **Step 2: Write backend/app/state_machines/fmea_state.py**

```python
from enum import Enum


class FMEAState(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REWORK = "rework"
    ARCHIVED = "archived"


class FMEAType(str, Enum):
    DFMEA = "DFMEA"
    PFMEA = "PFMEA"


FMEA_TRANSITIONS: dict[FMEAState, list[FMEAState]] = {
    FMEAState.DRAFT: [FMEAState.IN_REVIEW, FMEAState.ARCHIVED],
    FMEAState.IN_REVIEW: [FMEAState.APPROVED, FMEAState.REWORK],
    FMEAState.APPROVED: [FMEAState.REWORK, FMEAState.ARCHIVED],
    FMEAState.REWORK: [FMEAState.IN_REVIEW],
    FMEAState.ARCHIVED: [],
}


def can_transition(current: FMEAState, target: FMEAState) -> bool:
    return target in FMEA_TRANSITIONS.get(current, [])


def compute_rpn(severity: int, occurrence: int, detection: int) -> int:
    return severity * occurrence * detection


def compute_ap(rpn: int) -> str:
    if rpn >= 100:
        return "HIGH"
    elif rpn >= 50:
        return "MEDIUM"
    return "LOW"
```

- [ ] **Step 3: Write backend/app/state_machines/eightd_state.py**

```python
from enum import Enum


class EightDState(str, Enum):
    D1_TEAM = "D1_TEAM"
    D2_DESCRIPTION = "D2_DESCRIPTION"
    D3_INTERIM = "D3_INTERIM"
    D4_ROOT_CAUSE = "D4_ROOT_CAUSE"
    D5_CORRECTION = "D5_CORRECTION"
    D6_VERIFICATION = "D6_VERIFICATION"
    D7_PREVENTION = "D7_PREVENTION"
    D8_CLOSURE = "D8_CLOSURE"
    ARCHIVED = "ARCHIVED"


EIGHTD_TRANSITIONS: dict[EightDState, list[EightDState]] = {
    EightDState.D1_TEAM: [EightDState.D2_DESCRIPTION],
    EightDState.D2_DESCRIPTION: [EightDState.D3_INTERIM, EightDState.D1_TEAM],
    EightDState.D3_INTERIM: [EightDState.D4_ROOT_CAUSE],
    EightDState.D4_ROOT_CAUSE: [EightDState.D5_CORRECTION, EightDState.D3_INTERIM],
    EightDState.D5_CORRECTION: [EightDState.D6_VERIFICATION],
    EightDState.D6_VERIFICATION: [EightDState.D7_PREVENTION, EightDState.D5_CORRECTION],
    EightDState.D7_PREVENTION: [EightDState.D8_CLOSURE],
    EightDState.D8_CLOSURE: [EightDState.ARCHIVED],
    EightDState.ARCHIVED: [],
}


def can_transition(current: EightDState, target: EightDState) -> bool:
    return target in EIGHTD_TRANSITIONS.get(current, [])


EIGHTD_STEP_LABELS = {
    EightDState.D1_TEAM: "D1 团队组建",
    EightDState.D2_DESCRIPTION: "D2 问题描述",
    EightDState.D3_INTERIM: "D3 临时措施",
    EightDState.D4_ROOT_CAUSE: "D4 根因分析",
    EightDState.D5_CORRECTION: "D5 永久措施",
    EightDState.D6_VERIFICATION: "D6 实施验证",
    EightDState.D7_PREVENTION: "D7 预防复发",
    EightDState.D8_CLOSURE: "D8 关闭",
    EightDState.ARCHIVED: "已归档",
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/state_machines/
git commit -m "feat: port FMEA and 8D state machines from prototype"
```

---

### Task 9: FMEA Service & API

**Files:**
- Create: `backend/app/schemas/fmea.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/fmea_service.py`
- Create: `backend/app/api/fmea.py`

- [ ] **Step 1: Write backend/app/schemas/fmea.py**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class GraphNodeSchema(BaseModel):
    id: str
    type: str
    name: str
    process_number: str | None = None
    severity: int = 0
    occurrence: int = 0
    detection: int = 0


class GraphEdgeSchema(BaseModel):
    source: str
    target: str
    type: str


class GraphDataSchema(BaseModel):
    nodes: list[GraphNodeSchema] = []
    edges: list[GraphEdgeSchema] = []


class FMEACreate(BaseModel):
    title: str
    document_no: str
    fmea_type: str = "PFMEA"


class FMEAUpdate(BaseModel):
    title: str | None = None
    graph_data: GraphDataSchema | None = None


class FMEAResponse(BaseModel):
    fmea_id: uuid.UUID
    document_no: str
    title: str
    fmea_type: str
    product_line_code: str
    status: str
    version: int
    graph_data: dict
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}


class FMEAListResponse(BaseModel):
    items: list[FMEAResponse]
    total: int
    page: int
    page_size: int


class TransitionRequest(BaseModel):
    target_status: str
```

- [ ] **Step 2: Write backend/app/services/__init__.py**

```python
```

- [ ] **Step 3: Write backend/app/services/fmea_service.py**

```python
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.state_machines.fmea_state import FMEAState, can_transition


async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    count_query = select(func.count(FMEADocument.fmea_id))

    if status:
        query = query.where(FMEADocument.status == status)
        count_query = count_query.where(FMEADocument.status == status)

    query = query.order_by(FMEADocument.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_fmea(db: AsyncSession, fmea_id: uuid.UUID) -> FMEADocument | None:
    result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    return result.scalar_one_or_none()


async def create_fmea(
    db: AsyncSession, title: str, document_no: str, fmea_type: str, user_id: uuid.UUID
) -> FMEADocument:
    fmea = FMEADocument(
        title=title,
        document_no=document_no,
        fmea_type=fmea_type,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(fmea)
    await db.commit()
    await db.refresh(fmea)
    return fmea


async def update_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    title: str | None,
    graph_data: dict | None,
    user_id: uuid.UUID,
) -> FMEADocument:
    if title is not None:
        fmea.title = title
    if graph_data is not None:
        fmea.graph_data = graph_data
    fmea.updated_by = user_id
    await db.commit()
    await db.refresh(fmea)
    return fmea


async def transition_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    target_status: str,
    user_id: uuid.UUID,
) -> FMEADocument:
    current = FMEAState(fmea.status)
    target = FMEAState(target_status)

    if not can_transition(current, target):
        allowed = [s.value for s in FMEAState if can_transition(current, s)]
        raise ValueError(f"Cannot transition from {fmea.status} to {target_status}. Allowed: {allowed}")

    fmea.status = target_status
    fmea.updated_by = user_id

    if target == FMEAState.APPROVED:
        fmea.approved_by = user_id
        from datetime import datetime, timezone
        fmea.approved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(fmea)
    return fmea
```

- [ ] **Step 4: Write backend/app/api/fmea.py**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.fmea import (
    FMEACreate, FMEAUpdate, FMEAResponse, FMEAListResponse, TransitionRequest,
)
from app.services import fmea_service

router = APIRouter(prefix="/api/fmea", tags=["fmea"])


@router.get("", response_model=FMEAListResponse)
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await fmea_service.list_fmeas(db, page, page_size, status)
    return FMEAListResponse(
        items=[FMEAResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=FMEAResponse, status_code=201)
async def create_fmea(
    req: FMEACreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fmea = await fmea_service.create_fmea(db, req.title, req.document_no, req.fmea_type, user.user_id)
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}", response_model=FMEAResponse)
async def get_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    return FMEAResponse.model_validate(fmea)


@router.put("/{fmea_id}", response_model=FMEAResponse)
async def update_fmea(
    fmea_id: uuid.UUID,
    req: FMEAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    graph_dict = req.graph_data.model_dump() if req.graph_data else None
    fmea = await fmea_service.update_fmea(db, fmea, req.title, graph_dict, user.user_id)
    return FMEAResponse.model_validate(fmea)


@router.post("/{fmea_id}/transition", response_model=FMEAResponse)
async def transition_fmea(
    fmea_id: uuid.UUID,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    try:
        fmea = await fmea_service.transition_fmea(db, fmea, req.target_status, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}/graph")
async def get_fmea_graph(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    return fmea.graph_data
```

- [ ] **Step 5: Register FMEA routes in main.py**

In `backend/app/main.py`, add:

```python
from app.api.fmea import router as fmea_router

app.include_router(fmea_router)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/fmea.py backend/app/services/ backend/app/api/fmea.py backend/app/main.py
git commit -m "feat: add FMEA service and API endpoints"
```

---

### Task 10: 8D/CAPA Service & API

**Files:**
- Create: `backend/app/schemas/capa.py`
- Create: `backend/app/services/capa_service.py`
- Create: `backend/app/api/capa.py`

- [ ] **Step 1: Write backend/app/schemas/capa.py**

```python
import uuid
from datetime import date, datetime
from pydantic import BaseModel


class CAPACreate(BaseModel):
    title: str
    document_no: str
    severity: str = "一般"
    due_date: date | None = None


class CAPAUpdate(BaseModel):
    title: str | None = None
    d1_team: list[dict] | None = None
    d2_description: str | None = None
    d3_interim: str | None = None
    d4_root_cause: str | None = None
    d5_correction: str | None = None
    d6_verification: str | None = None
    d7_prevention: str | None = None
    d8_closure: str | None = None
    severity: str | None = None
    due_date: date | None = None
    fmea_ref_id: uuid.UUID | None = None


class CAPAResponse(BaseModel):
    report_id: uuid.UUID
    document_no: str
    title: str
    product_line_code: str
    status: str
    severity: str
    d1_team: list | None = None
    d2_description: str | None = None
    d3_interim: str | None = None
    d4_root_cause: str | None = None
    d5_correction: str | None = None
    d6_verification: str | None = None
    d7_prevention: str | None = None
    d8_closure: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    due_date: date | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CAPAListResponse(BaseModel):
    items: list[CAPAResponse]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: Write backend/app/services/capa_service.py**

```python
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa import CAPAEightD
from app.state_machines.eightd_state import EightDState, can_transition


async def list_capas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[CAPAEightD], int]:
    query = select(CAPAEightD)
    count_query = select(func.count(CAPAEightD.report_id))

    if status:
        query = query.where(CAPAEightD.status == status)
        count_query = count_query.where(CAPAEightD.status == status)

    query = query.order_by(CAPAEightD.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_capa(db: AsyncSession, report_id: uuid.UUID) -> CAPAEightD | None:
    result = await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == report_id))
    return result.scalar_one_or_none()


async def create_capa(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
) -> CAPAEightD:
    capa = CAPAEightD(
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        created_by=user_id,
    )
    db.add(capa)
    await db.commit()
    await db.refresh(capa)
    return capa


async def update_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    update_data: dict,
) -> CAPAEightD:
    for key, value in update_data.items():
        if value is not None and hasattr(capa, key):
            setattr(capa, key, value)
    await db.commit()
    await db.refresh(capa)
    return capa


async def advance_capa(
    db: AsyncSession,
    capa: CAPAEightD,
) -> CAPAEightD:
    current = EightDState(capa.status)
    transitions = [
        EightDState.D2_DESCRIPTION,
        EightDState.D3_INTERIM,
        EightDState.D4_ROOT_CAUSE,
        EightDState.D5_CORRECTION,
        EightDState.D6_VERIFICATION,
        EightDState.D7_PREVENTION,
        EightDState.D8_CLOSURE,
        EightDState.ARCHIVED,
    ]

    if current in transitions:
        idx = transitions.index(current)
        next_state = transitions[idx + 1] if idx + 1 < len(transitions) else EightDState.ARCHIVED
    else:
        raise ValueError(f"Cannot advance from {capa.status}")

    if not can_transition(current, next_state):
        raise ValueError(f"Cannot transition from {capa.status} to {next_state.value}")

    capa.status = next_state.value
    await db.commit()
    await db.refresh(capa)
    return capa


async def link_fmea(
    db: AsyncSession,
    capa: CAPAEightD,
    fmea_ref_id: uuid.UUID,
) -> CAPAEightD:
    capa.fmea_ref_id = fmea_ref_id
    await db.commit()
    await db.refresh(capa)
    return capa
```

- [ ] **Step 3: Write backend/app/api/capa.py**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.capa import CAPACreate, CAPAUpdate, CAPAResponse, CAPAListResponse
from app.services import capa_service

router = APIRouter(prefix="/api/capa", tags=["capa"])


@router.get("", response_model=CAPAListResponse)
async def list_capas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await capa_service.list_capas(db, page, page_size, status)
    return CAPAListResponse(
        items=[CAPAResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CAPAResponse, status_code=201)
async def create_capa(
    req: CAPACreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    capa = await capa_service.create_capa(
        db, req.title, req.document_no, req.severity, req.due_date, user.user_id
    )
    return CAPAResponse.model_validate(capa)


@router.get("/{report_id}", response_model=CAPAResponse)
async def get_capa(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    return CAPAResponse.model_validate(capa)


@router.put("/{report_id}", response_model=CAPAResponse)
async def update_capa(
    report_id: uuid.UUID,
    req: CAPAUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    capa = await capa_service.update_capa(db, capa, req.model_dump(exclude_unset=True))
    return CAPAResponse.model_validate(capa)


@router.post("/{report_id}/advance", response_model=CAPAResponse)
async def advance_capa(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    try:
        capa = await capa_service.advance_capa(db, capa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.post("/{report_id}/link-fmea", response_model=CAPAResponse)
async def link_fmea(
    report_id: uuid.UUID,
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    capa = await capa_service.link_fmea(db, capa, fmea_id)
    return CAPAResponse.model_validate(capa)
```

- [ ] **Step 4: Register CAPA routes in main.py**

In `backend/app/main.py`, add:

```python
from app.api.capa import router as capa_router

app.include_router(capa_router)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/capa.py backend/app/services/capa_service.py backend/app/api/capa.py backend/app/main.py
git commit -m "feat: add 8D/CAPA service and API endpoints"
```

---

### Task 11: Dashboard API

**Files:**
- Create: `backend/app/services/dashboard_service.py`
- Create: `backend/app/api/dashboard.py`

- [ ] **Step 1: Write backend/app/services/dashboard_service.py**

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD


async def get_dashboard(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)

    # FMEA counts
    total_fmea = await db.scalar(select(func.count(FMEADocument.fmea_id)))
    approved_fmea = await db.scalar(
        select(func.count(FMEADocument.fmea_id)).where(FMEADocument.status == "approved")
    )

    # CAPA counts
    total_capa = await db.scalar(select(func.count(CAPAEightD.report_id)))
    open_capa = await db.scalar(
        select(func.count(CAPAEightD.report_id)).where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
        )
    )

    # Overdue CAPAs
    overdue_capa = await db.scalar(
        select(func.count(CAPAEightD.report_id)).where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )
    )

    # Average RPN (from graph_data in FMEA)
    fmeas = await db.execute(select(FMEADocument.graph_data))
    total_rpn = 0
    rpn_count = 0
    for (graph_data,) in fmeas:
        for node in graph_data.get("nodes", []):
            if node.get("type") == "FailureMode":
                s = node.get("severity", 0)
                o = node.get("occurrence", 0)
                d = node.get("detection", 0)
                if s and o and d:
                    total_rpn += s * o * d
                    rpn_count += 1
    avg_rpn = round(total_rpn / rpn_count) if rpn_count > 0 else 0

    # High RPN alerts (RPN > 100)
    high_rpn_count = 0
    for (graph_data,) in fmeas:
        for node in graph_data.get("nodes", []):
            if node.get("type") == "FailureMode":
                rpn = node.get("severity", 0) * node.get("occurrence", 0) * node.get("detection", 0)
                if rpn >= 100:
                    high_rpn_count += 1

    return {
        "kpi": {
            "total_fmea": total_fmea or 0,
            "approved_fmea": approved_fmea or 0,
            "total_capa": total_capa or 0,
            "open_capa": open_capa or 0,
            "overdue_capa": overdue_capa or 0,
            "avg_rpn": avg_rpn,
            "high_rpn_count": high_rpn_count,
        },
        "trends": {
            "fmea_by_status": {
                "draft": 0,
                "in_review": 0,
                "approved": 0,
                "archived": 0,
            },
            "capa_by_status": {
                "open": open_capa or 0,
                "closed": (total_capa or 0) - (open_capa or 0),
            },
        },
        "alerts": [],
    }
```

- [ ] **Step 2: Write backend/app/api/dashboard.py**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await dashboard_service.get_dashboard(db)


@router.get("/kpi")
async def get_kpi(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db)
    return data["kpi"]


@router.get("/trends")
async def get_trends(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db)
    return data["trends"]


@router.get("/alerts")
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db)
    return data["alerts"]
```

- [ ] **Step 3: Register dashboard routes in main.py**

In `backend/app/main.py`, add:

```python
from app.api.dashboard import router as dashboard_router

app.include_router(dashboard_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/dashboard_service.py backend/app/api/dashboard.py backend/app/main.py
git commit -m "feat: add dashboard API with KPI, trends, and alerts"
```

---

## Phase 4: Frontend Pages

### Task 12: Frontend Types, API Client & Auth Store

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/store/authStore.ts`

- [ ] **Step 1: Write frontend/src/types/index.ts**

```typescript
export interface User {
  user_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role: string;
  is_active: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  process_number?: string;
  severity: number;
  occurrence: number;
  detection: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface FMEADocument {
  fmea_id: string;
  document_no: string;
  title: string;
  fmea_type: string;
  product_line_code: string;
  status: string;
  version: number;
  graph_data: GraphData;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export interface FMEAListResponse {
  items: FMEADocument[];
  total: number;
  page: number;
  page_size: number;
}

export interface CAPAReport {
  report_id: string;
  document_no: string;
  title: string;
  product_line_code: string;
  status: string;
  severity: string;
  d1_team: { name: string; role: string }[];
  d2_description: string | null;
  d3_interim: string | null;
  d4_root_cause: string | null;
  d5_correction: string | null;
  d6_verification: string | null;
  d7_prevention: string | null;
  d8_closure: string | null;
  fmea_ref_id: string | null;
  due_date: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CAPAListResponse {
  items: CAPAReport[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardData {
  kpi: {
    total_fmea: number;
    approved_fmea: number;
    total_capa: number;
    open_capa: number;
    overdue_capa: number;
    avg_rpn: number;
    high_rpn_count: number;
  };
  trends: Record<string, unknown>;
  alerts: unknown[];
}
```

- [ ] **Step 2: Write frontend/src/api/client.ts**

```typescript
import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default client;
```

- [ ] **Step 3: Write frontend/src/api/auth.ts**

```typescript
import client from "./client";
import type { LoginRequest, TokenResponse, User } from "../types";

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const resp = await client.post("/auth/login", data);
  return resp.data;
}

export async function getMe(): Promise<User> {
  const resp = await client.get("/auth/me");
  return resp.data;
}
```

- [ ] **Step 4: Write frontend/src/store/authStore.ts**

```typescript
import { create } from "zustand";
import type { User } from "../types";
import { login as apiLogin, getMe } from "../api/auth";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("access_token"),
  loading: false,

  login: async (username, password) => {
    const resp = await apiLogin({ username, password });
    localStorage.setItem("access_token", resp.access_token);
    set({ user: resp.user, token: resp.access_token });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    set({ user: null, token: null });
  },

  fetchUser: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
      set({ loading: true });
      const user = await getMe();
      set({ user, loading: false });
    } catch {
      localStorage.removeItem("access_token");
      set({ user: null, token: null, loading: false });
    }
  },
}));
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/ frontend/src/api/ frontend/src/store/
git commit -m "feat: add frontend types, API client, and auth store"
```

---

### Task 13: App Layout, Login Page & Auth Guard

**Files:**
- Create: `frontend/src/pages/login/LoginPage.tsx`
- Create: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write frontend/src/pages/login/LoginPage.tsx**

```typescript
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Form, Input, Button, Card, Typography, message, Space } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";

const { Title, Text } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success("登录成功");
      navigate("/dashboard", { replace: true });
    } catch {
      message.error("用户名或密码错误");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      <Card style={{ width: 400, boxShadow: "0 8px 24px rgba(0,0,0,0.15)" }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div style={{ textAlign: "center" }}>
            <Title level={3} style={{ margin: 0 }}>
              OpenQMS
            </Title>
            <Text type="secondary">智能质量管理平台</Text>
          </div>
          <Form onFinish={onFinish} size="large">
            <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登录
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary" style={{ display: "block", textAlign: "center", fontSize: 12 }}>
            默认账号: admin / Admin@2026
          </Text>
        </Space>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Write frontend/src/components/layout/AppLayout.tsx**

```typescript
import { useState } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Avatar, Dropdown, theme } from "antd";
import {
  DashboardOutlined,
  FileTextOutlined,
  BugOutlined,
  LogoutOutlined,
  UserOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/fmea", icon: <FileTextOutlined />, label: "FMEA管理" },
  { key: "/capa", icon: <BugOutlined />, label: "8D/CAPA" },
];

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { token: themeToken } = theme.useToken();

  const selectedKey = "/" + location.pathname.split("/")[1];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        style={{ background: themeToken.colorBgContainer }}
      >
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: collapsed ? 16 : 20,
            color: themeToken.colorPrimary,
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
          }}
        >
          {collapsed ? "QMS" : "OpenQMS"}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 24px",
            background: themeToken.colorBgContainer,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: `1px solid ${themeToken.colorBorderSecondary}`,
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <Dropdown
            menu={{
              items: [
                { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: () => { logout(); navigate("/login"); } },
              ],
            }}
          >
            <Space style={{ cursor: "pointer" }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.display_name || user?.username}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
```

- [ ] **Step 3: Update frontend/src/App.tsx**

```typescript
import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Spin } from "antd";
import { useAuthStore } from "./store/authStore";
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./pages/login/LoginPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const loading = useAuthStore((s) => s.loading);
  const fetchUser = useAuthStore((s) => s.fetchUser);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (token && !user) fetchUser();
  }, [token, user, fetchUser]);

  if (token && !user) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route path="/fmea" element={<div>FMEA List</div>} />
        <Route path="/fmea/:id" element={<div>FMEA Editor</div>} />
        <Route path="/capa" element={<div>CAPA List</div>} />
        <Route path="/capa/:id" element={<div>CAPA Detail</div>} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/login/ frontend/src/components/layout/ frontend/src/App.tsx
git commit -m "feat: add login page, app layout with sidebar, and auth guard"
```

---

### Task 14: Dashboard Page

**Files:**
- Create: `frontend/src/api/dashboard.ts`
- Create: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Create: `frontend/src/components/shared/KPICard.tsx`
- Modify: `frontend/src/App.tsx` (replace dashboard placeholder)

- [ ] **Step 1: Write frontend/src/api/dashboard.ts**

```typescript
import client from "./client";
import type { DashboardData } from "../types";

export async function getDashboard(): Promise<DashboardData> {
  const resp = await client.get("/dashboard");
  return resp.data;
}
```

- [ ] **Step 2: Write frontend/src/components/shared/KPICard.tsx**

```typescript
import { Card, Statistic } from "antd";

interface KPICardProps {
  title: string;
  value: number;
  suffix?: string;
  color?: string;
}

export default function KPICard({ title, value, suffix, color }: KPICardProps) {
  return (
    <Card>
      <Statistic
        title={title}
        value={value}
        suffix={suffix}
        valueStyle={{ color: color || "#1677FF", fontSize: 28 }}
      />
    </Card>
  );
}
```

- [ ] **Step 3: Write frontend/src/pages/dashboard/DashboardPage.tsx**

```typescript
import { useEffect, useState } from "react";
import { Row, Col, Card, Table, Tag, Typography } from "antd";
import {
  FileTextOutlined,
  CheckCircleOutlined,
  BugOutlined,
  ClockCircleOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { getDashboard } from "../../api/dashboard";
import KPICard from "../../components/shared/KPICard";
import type { DashboardData } from "../../types";

const { Title } = Typography;

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboard()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  const kpi = data?.kpi;

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        质量仪表盘
      </Title>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="FMEA 文档总数"
            value={kpi?.total_fmea ?? 0}
            color="#1677FF"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="已批准 FMEA"
            value={kpi?.approved_fmea ?? 0}
            color="#52C41A"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="开放 8D 报告"
            value={kpi?.open_capa ?? 0}
            color="#FAAD14"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="超期 8D"
            value={kpi?.overdue_capa ?? 0}
            color={kpi && kpi.overdue_capa > 0 ? "#FF4D4F" : "#52C41A"}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="平均 RPN"
            value={kpi?.avg_rpn ?? 0}
            color={kpi && kpi.avg_rpn >= 100 ? "#FF4D4F" : kpi && kpi.avg_rpn >= 50 ? "#FAAD14" : "#52C41A"}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="高风险项 (RPN≥100)"
            value={kpi?.high_rpn_count ?? 0}
            color={kpi && kpi.high_rpn_count > 0 ? "#FF4D4F" : "#52C41A"}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <KPICard
            title="8D 报告总数"
            value={kpi?.total_capa ?? 0}
            color="#1677FF"
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="数据概览" loading={loading}>
            <Table
              dataSource={[
                { key: "fmea", metric: "FMEA 文档", total: kpi?.total_fmea ?? 0, approved: kpi?.approved_fmea ?? 0 },
                { key: "capa", metric: "8D 报告", total: kpi?.total_capa ?? 0, open: kpi?.open_capa ?? 0, overdue: kpi?.overdue_capa ?? 0 },
                { key: "rpn", metric: "风险指标", avg_rpn: kpi?.avg_rpn ?? 0, high_risk: kpi?.high_rpn_count ?? 0 },
              ]}
              columns={[
                { title: "指标", dataIndex: "metric", key: "metric" },
                { title: "总数", dataIndex: "total", key: "total", render: (v: number) => v ?? "-" },
                { title: "已批准", dataIndex: "approved", key: "approved", render: (v: number) => v ?? "-" },
                {
                  title: "进行中",
                  dataIndex: "open",
                  key: "open",
                  render: (v: number) =>
                    v !== undefined ? <Tag color="processing">{v}</Tag> : "-",
                },
                {
                  title: "超期",
                  dataIndex: "overdue",
                  key: "overdue",
                  render: (v: number) =>
                    v !== undefined && v > 0 ? <Tag color="error">{v}</Tag> : v === 0 ? <Tag color="success">0</Tag> : "-",
                },
                {
                  title: "平均 RPN",
                  dataIndex: "avg_rpn",
                  key: "avg_rpn",
                  render: (v: number) => (v !== undefined ? v : "-"),
                },
                {
                  title: "高风险",
                  dataIndex: "high_risk",
                  key: "high_risk",
                  render: (v: number) =>
                    v !== undefined && v > 0 ? <Tag color="error">{v}</Tag> : v === 0 ? <Tag color="success">0</Tag> : "-",
                },
              ]}
              pagination={false}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 4: Update App.tsx dashboard route**

In `frontend/src/App.tsx`, add import and replace dashboard placeholder:

```typescript
import DashboardPage from "./pages/dashboard/DashboardPage";

// Replace: <Route path="/dashboard" element={<div>Dashboard</div>} />
// With:
<Route path="/dashboard" element={<DashboardPage />} />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/dashboard.ts frontend/src/pages/dashboard/ frontend/src/components/shared/ frontend/src/App.tsx
git commit -m "feat: add dashboard page with KPI cards and summary table"
```

---

### Task 15: FMEA List Page

**Files:**
- Create: `frontend/src/api/fmea.ts`
- Create: `frontend/src/pages/fmea/FMEAListPage.tsx`
- Modify: `frontend/src/App.tsx` (replace FMEA list placeholder)

- [ ] **Step 1: Write frontend/src/api/fmea.ts**

```typescript
import client from "./client";
import type { FMEADocument, FMEAListResponse, GraphData } from "../types";

export async function listFMEAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<FMEAListResponse> {
  const resp = await client.get("/fmea", { params });
  return resp.data;
}

export async function getFMEA(id: string): Promise<FMEADocument> {
  const resp = await client.get(`/fmea/${id}`);
  return resp.data;
}

export async function createFMEA(data: {
  title: string;
  document_no: string;
  fmea_type: string;
}): Promise<FMEADocument> {
  const resp = await client.post("/fmea", data);
  return resp.data;
}

export async function updateFMEA(
  id: string,
  data: { title?: string; graph_data?: GraphData }
): Promise<FMEADocument> {
  const resp = await client.put(`/fmea/${id}`, data);
  return resp.data;
}

export async function transitionFMEA(
  id: string,
  target_status: string
): Promise<FMEADocument> {
  const resp = await client.post(`/fmea/${id}/transition`, { target_status });
  return resp.data;
}
```

- [ ] **Step 2: Write frontend/src/pages/fmea/FMEAListPage.tsx**

```typescript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Tag, Space, Typography, Modal, Form, Input, Select, message } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { listFMEAs, createFMEA } from "../../api/fmea";
import type { FMEADocument } from "../../types";

const { Title } = Typography;

const statusColors: Record<string, string> = {
  draft: "default",
  in_review: "processing",
  approved: "success",
  rework: "warning",
  archived: "default",
};

const statusLabels: Record<string, string> = {
  draft: "草稿",
  in_review: "审核中",
  approved: "已批准",
  rework: "返工中",
  archived: "已归档",
};

export default function FMEAListPage() {
  const [data, setData] = useState<FMEADocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const fetchData = (p: number = page) => {
    setLoading(true);
    listFMEAs({ page: p, page_size: 20 })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreate = async (values: { title: string; document_no: string }) => {
    try {
      const fmea = await createFMEA({
        ...values,
        fmea_type: "PFMEA",
      });
      message.success("FMEA 创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/fmea/${fmea.fmea_id}`);
    } catch {
      message.error("创建失败");
    }
  };

  const columns = [
    {
      title: "文档编号",
      dataIndex: "document_no",
      key: "document_no",
      width: 150,
    },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    {
      title: "类型",
      dataIndex: "fmea_type",
      key: "fmea_type",
      width: 80,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColors[s] || "default"}>{statusLabels[s] || s}</Tag>,
    },
    {
      title: "版本",
      dataIndex: "version",
      key: "version",
      width: 60,
      render: (v: number) => `v${v}`,
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      key: "actions",
      width: 100,
      render: (_: unknown, record: FMEADocument) => (
        <Button
          type="link"
          icon={<FileTextOutlined />}
          onClick={() => navigate(`/fmea/${record.fmea_id}`)}
        >
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          FMEA 管理
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建 PFMEA
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="fmea_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p);
          },
        }}
      />

      <Modal
        title="新建 PFMEA"
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="document_no"
            label="文档编号"
            rules={[{ required: true, message: "请输入文档编号" }]}
          >
            <Input placeholder="如 PFMEA-2026-001" />
          </Form.Item>
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: "请输入标题" }]}
          >
            <Input placeholder="如 SMT焊接工序PFMEA" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 5: Update App.tsx FMEA list route**

In `frontend/src/App.tsx`:

```typescript
import FMEAListPage from "./pages/fmea/FMEAListPage";

// Replace: <Route path="/fmea" element={<div>FMEA List</div>} />
// With:
<Route path="/fmea" element={<FMEAListPage />} />
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/fmea.ts frontend/src/pages/fmea/FMEAListPage.tsx frontend/src/App.tsx
git commit -m "feat: add FMEA list page with create modal"
```

---

### Task 16: FMEA Editor Page

**Files:**
- Create: `frontend/src/pages/fmea/FMEAEditorPage.tsx`
- Modify: `frontend/src/App.tsx` (replace FMEA editor placeholder)

- [ ] **Step 1: Write frontend/src/pages/fmea/FMEAEditorPage.tsx**

```typescript
import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Input, Select, Table, Card,
  Row, Col, Divider, message, Spin, Popconfirm, Empty,
} from "antd";
import {
  SaveOutlined, ArrowLeftOutlined, SendOutlined,
  CheckOutlined, UndoOutlined, PlusOutlined, DeleteOutlined,
  NodeIndexOutlined,
} from "@ant-design/icons";
import { getFMEA, updateFMEA, transitionFMEA } from "../../api/fmea";
import type { FMEADocument, GraphNode, GraphEdge } from "../../types";

const { Title, Text } = Typography;

const nodeTypes = [
  { value: "Process", label: "工序" },
  { value: "Function", label: "功能" },
  { value: "FailureMode", label: "失效模式" },
  { value: "FailureCause", label: "失效原因" },
  { value: "FailureEffect", label: "失效影响" },
  { value: "ControlMeasure", label: "控制措施" },
];

const edgeTypes = [
  { value: "HAS_FUNCTION", label: "包含功能" },
  { value: "HAS_FAILURE_MODE", label: "存在失效模式" },
  { value: "HAS_CAUSE", label: "失效原因" },
  { value: "HAS_EFFECT", label: "失效影响" },
  { value: "CONTROLLED_BY", label: "控制措施" },
  { value: "DETECTED_BY", label: "检测措施" },
];

const statusLabels: Record<string, string> = {
  draft: "草稿", in_review: "审核中", approved: "已批准",
  rework: "返工中", archived: "已归档",
};

const nextTransitions: Record<string, { label: string; target: string; icon: React.ReactNode }[]> = {
  draft: [
    { label: "提交审核", target: "in_review", icon: <SendOutlined /> },
    { label: "归档", target: "archived", icon: <CheckOutlined /> },
  ],
  in_review: [
    { label: "批准", target: "approved", icon: <CheckOutlined /> },
    { label: "打回修改", target: "rework", icon: <UndoOutlined /> },
  ],
  approved: [
    { label: "打回修改", target: "rework", icon: <UndoOutlined /> },
    { label: "归档", target: "archived", icon: <CheckOutlined /> },
  ],
  rework: [
    { label: "重新提交", target: "in_review", icon: <SendOutlined /> },
  ],
};

export default function FMEAEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [fmea, setFmea] = useState<FMEADocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedProcessId, setSelectedProcessId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getFMEA(id)
      .then((doc) => {
        setFmea(doc);
        setNodes(doc.graph_data?.nodes || []);
        setEdges(doc.graph_data?.edges || []);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const save = useCallback(async () => {
    if (!id || !fmea) return;
    setSaving(true);
    try {
      const updated = await updateFMEA(id, {
        title: fmea.title,
        graph_data: { nodes, edges },
      });
      setFmea(updated);
      message.success("保存成功");
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  }, [id, fmea, nodes, edges]);

  const handleTransition = async (target: string) => {
    if (!id) return;
    try {
      const updated = await transitionFMEA(id, target);
      setFmea(updated);
      message.success(`状态已变更为: ${statusLabels[target] || target}`);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || "操作失败");
    }
  };

  const addNode = () => {
    const type = selectedProcessId ? "Function" : "Process";
    const name = type === "Process" ? `OP${(nodes.filter(n => n.type === "Process").length + 1) * 10}` : "新节点";
    setNodes([...nodes, { id: `n${Date.now()}`, type, name, severity: 0, occurrence: 0, detection: 0 }]);
  };

  const deleteNode = (nodeId: string) => {
    setNodes(nodes.filter((n) => n.id !== nodeId));
    setEdges(edges.filter((e) => e.source !== nodeId && e.target !== nodeId));
  };

  const updateNode = (nodeId: string, field: string, value: unknown) => {
    setNodes(nodes.map((n) => (n.id === nodeId ? { ...n, [field]: value } : n)));
  };

  const addEdge = () => {
    if (nodes.length < 2) {
      message.warning("需要至少两个节点才能添加关系");
      return;
    }
    setEdges([...edges, { source: nodes[0].id, target: nodes[1].id, type: "HAS_FUNCTION" }]);
  };

  const deleteEdge = (index: number) => {
    setEdges(edges.filter((_, i) => i !== index));
  };

  const processNodes = nodes.filter((n) => n.type === "Process");

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!fmea) return <Empty description="FMEA 未找到" />;

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/fmea")}>返回</Button>
          <Title level={4} style={{ margin: 0 }}>
            {fmea.title}
          </Title>
          <Tag>{statusLabels[fmea.status] || fmea.status}</Tag>
          <Text type="secondary">{fmea.document_no} v{fmea.version}</Text>
        </Space>
        <Space>
          {nextTransitions[fmea.status]?.map((t) => (
            <Popconfirm
              key={t.target}
              title={`确认${t.label}？`}
              onConfirm={() => handleTransition(t.target)}
            >
              <Button icon={t.icon}>{t.label}</Button>
            </Popconfirm>
          ))}
          <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving}>
            保存
          </Button>
        </Space>
      </div>

      <Row gutter={16}>
        {/* Left: Process Flow */}
        <Col span={6}>
          <Card
            title="工序流"
            size="small"
            extra={<Button size="small" icon={<PlusOutlined />} onClick={addNode}>添加工序</Button>}
          >
            {processNodes.map((node) => (
              <div
                key={node.id}
                onClick={() => setSelectedProcessId(node.id)}
                style={{
                  padding: "8px 12px",
                  marginBottom: 8,
                  borderRadius: 6,
                  cursor: "pointer",
                  background: selectedProcessId === node.id ? "#e6f4ff" : "#f5f5f5",
                  border: selectedProcessId === node.id ? "1px solid #1677FF" : "1px solid #d9d9d9",
                }}
              >
                <div style={{ fontWeight: 600 }}>{node.name}</div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {node.process_number}
                </Text>
              </div>
            ))}
            {processNodes.length === 0 && (
              <Empty description="暂无工序，点击上方按钮添加" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* Right: Nodes & Edges */}
        <Col span={18}>
          <Card
            title="FMEA 数据"
            size="small"
            extra={
              <Space>
                <Button size="small" icon={<PlusOutlined />} onClick={addNode}>添加节点</Button>
                <Button size="small" icon={<NodeIndexOutlined />} onClick={addEdge}>添加关系</Button>
              </Space>
            }
          >
            {/* Node Table */}
            <Table
              dataSource={nodes}
              rowKey="id"
              size="small"
              pagination={false}
              scroll={{ y: 300 }}
              columns={[
                {
                  title: "类型", dataIndex: "type", key: "type", width: 120,
                  render: (t: string, record: GraphNode) => (
                    <Select
                      value={t}
                      size="small"
                      style={{ width: 110 }}
                      options={nodeTypes}
                      onChange={(v) => updateNode(record.id, "type", v)}
                    />
                  ),
                },
                {
                  title: "名称", dataIndex: "name", key: "name",
                  render: (t: string, record: GraphNode) => (
                    <Input
                      value={t}
                      size="small"
                      onChange={(e) => updateNode(record.id, "name", e.target.value)}
                    />
                  ),
                },
                {
                  title: "工序号", dataIndex: "process_number", key: "process_number", width: 100,
                  render: (t: string, record: GraphNode) =>
                    record.type === "Process" ? (
                      <Input
                        value={t}
                        size="small"
                        onChange={(e) => updateNode(record.id, "process_number", e.target.value)}
                      />
                    ) : null,
                },
                {
                  title: "S", key: "severity", width: 60,
                  render: (_: unknown, record: GraphNode) =>
                    record.type === "FailureMode" ? (
                      <Input
                        size="small"
                        type="number"
                        min={1} max={10}
                        value={record.severity || ""}
                        onChange={(e) => updateNode(record.id, "severity", Number(e.target.value))}
                      />
                    ) : null,
                },
                {
                  title: "O", key: "occurrence", width: 60,
                  render: (_: unknown, record: GraphNode) =>
                    record.type === "FailureMode" ? (
                      <Input
                        size="small"
                        type="number"
                        min={1} max={10}
                        value={record.occurrence || ""}
                        onChange={(e) => updateNode(record.id, "occurrence", Number(e.target.value))}
                      />
                    ) : null,
                },
                {
                  title: "D", key: "detection", width: 60,
                  render: (_: unknown, record: GraphNode) =>
                    record.type === "FailureMode" ? (
                      <Input
                        size="small"
                        type="number"
                        min={1} max={10}
                        value={record.detection || ""}
                        onChange={(e) => updateNode(record.id, "detection", Number(e.target.value))}
                      />
                    ) : null,
                },
                {
                  title: "RPN", key: "rpn", width: 70,
                  render: (_: unknown, record: GraphNode) => {
                    if (record.type !== "FailureMode") return null;
                    const rpn = record.severity * record.occurrence * record.detection;
                    const color = rpn >= 100 ? "#FF4D4F" : rpn >= 50 ? "#FAAD14" : "#52C41A";
                    return <Tag color={color}>{rpn || 0}</Tag>;
                  },
                },
                {
                  title: "", key: "actions", width: 40,
                  render: (_: unknown, record: GraphNode) => (
                    <Button
                      type="text"
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={() => deleteNode(record.id)}
                    />
                  ),
                },
              ]}
            />

            <Divider orientation="left" plain style={{ fontSize: 13 }}>
              关系 (Edges)
            </Divider>

            {/* Edge Table */}
            <Table
              dataSource={edges}
              rowKey={(_, i) => String(i)}
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
              columns={[
                {
                  title: "源节点", key: "source", width: 200,
                  render: (_: unknown, record: GraphEdge) => (
                    <Select
                      value={record.source}
                      size="small"
                      style={{ width: 180 }}
                      onChange={(v) => {
                        const newEdges = [...edges];
                        const idx = newEdges.indexOf(record);
                        newEdges[idx] = { ...newEdges[idx], source: v };
                        setEdges(newEdges);
                      }}
                      options={nodes.map((n) => ({ value: n.id, label: `${n.name} (${n.type})` }))}
                    />
                  ),
                },
                {
                  title: "关系类型", key: "type", width: 150,
                  render: (_: unknown, record: GraphEdge) => (
                    <Select
                      value={record.type}
                      size="small"
                      style={{ width: 130 }}
                      options={edgeTypes}
                      onChange={(v) => {
                        const newEdges = [...edges];
                        const idx = newEdges.indexOf(record);
                        newEdges[idx] = { ...newEdges[idx], type: v };
                        setEdges(newEdges);
                      }}
                    />
                  ),
                },
                {
                  title: "目标节点", key: "target", width: 200,
                  render: (_: unknown, record: GraphEdge) => (
                    <Select
                      value={record.target}
                      size="small"
                      style={{ width: 180 }}
                      onChange={(v) => {
                        const newEdges = [...edges];
                        const idx = newEdges.indexOf(record);
                        newEdges[idx] = { ...newEdges[idx], target: v };
                        setEdges(newEdges);
                      }}
                      options={nodes.map((n) => ({ value: n.id, label: `${n.name} (${n.type})` }))}
                    />
                  ),
                },
                {
                  title: "", key: "actions", width: 40,
                  render: (_: unknown, _record: GraphEdge, index: number) => (
                    <Button
                      type="text"
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={() => deleteEdge(index)}
                    />
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx FMEA editor route**

In `frontend/src/App.tsx`:

```typescript
import FMEAEditorPage from "./pages/fmea/FMEAEditorPage";

// Replace: <Route path="/fmea/:id" element={<div>FMEA Editor</div>} />
// With:
<Route path="/fmea/:id" element={<FMEAEditorPage />} />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/fmea/FMEAEditorPage.tsx frontend/src/App.tsx
git commit -m "feat: add FMEA editor page with node/edge management and state transitions"
```

---

### Task 17: 8D/CAPA List & Detail Pages

**Files:**
- Create: `frontend/src/api/capa.ts`
- Create: `frontend/src/pages/capa/CAPAListPage.tsx`
- Create: `frontend/src/pages/capa/CAPADetailPage.tsx`
- Modify: `frontend/src/App.tsx` (replace CAPA placeholders)

- [ ] **Step 1: Write frontend/src/api/capa.ts**

```typescript
import client from "./client";
import type { CAPAReport, CAPAListResponse } from "../types";

export async function listCAPAs(params: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<CAPAListResponse> {
  const resp = await client.get("/capa", { params });
  return resp.data;
}

export async function getCAPA(id: string): Promise<CAPAReport> {
  const resp = await client.get(`/capa/${id}`);
  return resp.data;
}

export async function createCAPA(data: {
  title: string;
  document_no: string;
  severity: string;
  due_date?: string;
}): Promise<CAPAReport> {
  const resp = await client.post("/capa", data);
  return resp.data;
}

export async function updateCAPA(
  id: string,
  data: Record<string, unknown>
): Promise<CAPAReport> {
  const resp = await client.put(`/capa/${id}`, data);
  return resp.data;
}

export async function advanceCAPA(id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/advance`);
  return resp.data;
}

export async function linkFMEA(id: string, fmea_id: string): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/link-fmea`, null, {
    params: { fmea_id },
  });
  return resp.data;
}
```

- [ ] **Step 2: Write frontend/src/pages/capa/CAPAListPage.tsx**

```typescript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Tag, Space, Typography, Modal, Form, Input, Select, DatePicker, message } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { listCAPAs, createCAPA } from "../../api/capa";
import type { CAPAReport } from "../../types";

const { Title } = Typography;

const severityColors: Record<string, string> = {
  "致命": "red", "严重": "orange", "一般": "blue", "轻微": "default",
};

const statusLabels: Record<string, string> = {
  D1_TEAM: "D1 团队组建", D2_DESCRIPTION: "D2 问题描述",
  D3_INTERIM: "D3 临时措施", D4_ROOT_CAUSE: "D4 根因分析",
  D5_CORRECTION: "D5 永久措施", D6_VERIFICATION: "D6 实施验证",
  D7_PREVENTION: "D7 预防复发", D8_CLOSURE: "D8 关闭", ARCHIVED: "已归档",
};

export default function CAPAListPage() {
  const [data, setData] = useState<CAPAReport[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const fetchData = (p: number = page) => {
    setLoading(true);
    listCAPAs({ page: p, page_size: 20 })
      .then((res) => { setData(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreate = async (values: { title: string; document_no: string; severity: string; due_date?: string }) => {
    try {
      const capa = await createCAPA(values);
      message.success("8D 报告创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/capa/${capa.report_id}`);
    } catch { message.error("创建失败"); }
  };

  const columns = [
    { title: "报告编号", dataIndex: "document_no", key: "document_no", width: 150 },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    {
      title: "当前步骤", dataIndex: "status", key: "status", width: 140,
      render: (s: string) => <Tag color="processing">{statusLabels[s] || s}</Tag>,
    },
    {
      title: "严重等级", dataIndex: "severity", key: "severity", width: 90,
      render: (s: string) => <Tag color={severityColors[s] || "default"}>{s}</Tag>,
    },
    {
      title: "期限", dataIndex: "due_date", key: "due_date", width: 110,
      render: (v: string | null) => v || "-",
    },
    {
      title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作", key: "actions", width: 80,
      render: (_: unknown, record: CAPAReport) => (
        <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/capa/${record.report_id}`)}>
          处理
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>8D / CAPA</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建 8D</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="report_id" loading={loading}
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p); } }}
      />
      <Modal title="新建 8D 报告" open={modalOpen} onOk={() => form.submit()} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label="报告编号" rules={[{ required: true }]}>
            <Input placeholder="如 8D-2026-001" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="如 焊接不良客诉" />
          </Form.Item>
          <Form.Item name="severity" label="严重等级" initialValue="一般">
            <Select options={["致命", "严重", "一般", "轻微"].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="due_date" label="完成期限">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 3: Write frontend/src/pages/capa/CAPADetailPage.tsx**

```typescript
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Steps, Card, Form, Input,
  Select, DatePicker, message, Spin, Empty, Row, Col,
} from "antd";
import { ArrowLeftOutlined, ArrowRightOutlined, SaveOutlined, LinkOutlined } from "@ant-design/icons";
import { getCAPA, updateCAPA, advanceCAPA, linkFMEA } from "../../api/capa";
import { listFMEAs } from "../../api/fmea";
import type { CAPAReport, FMEADocument } from "../../types";

const { Title, Text } = Typography;
const { TextArea } = Input;

const stepItems = [
  { title: "D1 团队组建" }, { title: "D2 问题描述" },
  { title: "D3 临时措施" }, { title: "D4 根因分析" },
  { title: "D5 永久措施" }, { title: "D6 实施验证" },
  { title: "D7 预防复发" }, { title: "D8 关闭" },
];

const stepIndex: Record<string, number> = {
  D1_TEAM: 0, D2_DESCRIPTION: 1, D3_INTERIM: 2, D4_ROOT_CAUSE: 3,
  D5_CORRECTION: 4, D6_VERIFICATION: 5, D7_PREVENTION: 6, D8_CLOSURE: 7, ARCHIVED: 8,
};

export default function CAPADetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [capa, setCapa] = useState<CAPAReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [fmeas, setFmeas] = useState<FMEADocument[]>([]);
  const [linkModal, setLinkModal] = useState(false);

  useEffect(() => {
    if (!id) return;
    getCAPA(id).then(setCapa).finally(() => setLoading(false));
    listFMEAs({ page_size: 100 }).then((res) => setFmeas(res.items));
  }, [id]);

  const currentStep = capa ? (stepIndex[capa.status] ?? 0) : 0;

  const handleUpdate = async (field: string, value: unknown) => {
    if (!id) return;
    setSaving(true);
    try {
      const updated = await updateCAPA(id, { [field]: value });
      setCapa(updated);
    } catch { message.error("保存失败"); }
    setSaving(false);
  };

  const handleAdvance = async () => {
    if (!id) return;
    try {
      const updated = await advanceCAPA(id);
      setCapa(updated);
      message.success("已推进到下一步");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || "推进失败");
    }
  };

  const handleLinkFMEA = async (fmeaId: string) => {
    if (!id) return;
    try {
      const updated = await linkFMEA(id, fmeaId);
      setCapa(updated);
      setLinkModal(false);
      message.success("已关联 FMEA");
    } catch { message.error("关联失败"); }
  };

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!capa) return <Empty description="8D 报告未找到" />;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/capa")}>返回</Button>
          <Title level={4} style={{ margin: 0 }}>{capa.title}</Title>
          <Tag color="blue">{capa.document_no}</Tag>
          <Tag color="red">{capa.severity}</Tag>
        </Space>
        <Space>
          {capa.fmea_ref_id && (
            <Tag icon={<LinkOutlined />} color="green">已关联 FMEA</Tag>
          )}
          <Button icon={<LinkOutlined />} onClick={() => setLinkModal(true)}>
            {capa.fmea_ref_id ? "更换FMEA关联" : "关联FMEA"}
          </Button>
          {capa.status !== "ARCHIVED" && capa.status !== "D8_CLOSURE" && (
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleAdvance}>
              推进下一步
            </Button>
          )}
        </Space>
      </div>

      <Steps current={currentStep} items={stepItems} style={{ marginBottom: 24 }} />

      <Row gutter={16}>
        <Col span={16}>
          <Card title="当前步骤详情">
            {/* D1: Team */}
            {capa.status === "D1_TEAM" && (
              <Form layout="vertical">
                <Form.Item label="团队成员 (JSON)">
                  <TextArea
                    rows={4}
                    value={JSON.stringify(capa.d1_team, null, 2)}
                    onChange={(e) => {
                      try {
                        const parsed = JSON.parse(e.target.value);
                        handleUpdate("d1_team", parsed);
                      } catch { /* allow editing */ }
                    }}
                  />
                </Form.Item>
              </Form>
            )}

            {/* D2: Description */}
            {capa.status === "D2_DESCRIPTION" && (
              <Form layout="vertical">
                <Form.Item label="5W2H 问题描述">
                  <TextArea
                    rows={6}
                    value={capa.d2_description || ""}
                    onChange={(e) => handleUpdate("d2_description", e.target.value)}
                    placeholder="What / Who / When / Where / Why / How / How much"
                  />
                </Form.Item>
              </Form>
            )}

            {/* D3: Interim */}
            {capa.status === "D3_INTERIM" && (
              <Form layout="vertical">
                <Form.Item label="临时遏制措施">
                  <TextArea
                    rows={4}
                    value={capa.d3_interim || ""}
                    onChange={(e) => handleUpdate("d3_interim", e.target.value)}
                  />
                </Form.Item>
              </Form>
            )}

            {/* D4: Root Cause */}
            {capa.status === "D4_ROOT_CAUSE" && (
              <Form layout="vertical">
                <Form.Item label="根因分析 (5Why / 鱼骨图)">
                  <TextArea
                    rows={6}
                    value={capa.d4_root_cause || ""}
                    onChange={(e) => handleUpdate("d4_root_cause", e.target.value)}
                  />
                </Form.Item>
              </Form>
            )}

            {/* D5: Correction */}
            {capa.status === "D5_CORRECTION" && (
              <Form layout="vertical">
                <Form.Item label="永久纠正措施">
                  <TextArea
                    rows={4}
                    value={capa.d5_correction || ""}
                    onChange={(e) => handleUpdate("d5_correction", e.target.value)}
                  />
                </Form.Item>
              </Form>
            )}

            {/* D6: Verification */}
            {capa.status === "D6_VERIFICATION" && (
              <Form layout="vertical">
                <Form.Item label="效果验证">
                  <TextArea
                    rows={4}
                    value={capa.d6_verification || ""}
                    onChange={(e) => handleUpdate("d6_verification", e.target.value)}
                  />
                </Form.Item>
              </Form>
            )}

            {/* D7: Prevention */}
            {capa.status === "D7_PREVENTION" && (
              <Form layout="vertical">
                <Form.Item label="预防复发措施">
                  <TextArea
                    rows={4}
                    value={capa.d7_prevention || ""}
                    onChange={(e) => handleUpdate("d7_prevention", e.target.value)}
                  />
                </Form.Item>
              </Form>
            )}

            {/* D8: Closure */}
            {capa.status === "D8_CLOSURE" && (
              <Form layout="vertical">
                <Form.Item label="关闭确认">
                  <TextArea
                    rows={4}
                    value={capa.d8_closure || ""}
                    onChange={(e) => handleUpdate("d8_closure", e.target.value)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "ARCHIVED" && (
              <Empty description="报告已归档" />
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card title="报告信息" size="small">
            <p><Text strong>编号:</Text> {capa.document_no}</p>
            <p><Text strong>严重等级:</Text> <Tag color="red">{capa.severity}</Tag></p>
            <p><Text strong>期限:</Text> {capa.due_date || "未设定"}</p>
            <p><Text strong>关联 FMEA:</Text> {capa.fmea_ref_id || "未关联"}</p>
            <p><Text strong>创建时间:</Text> {new Date(capa.created_at).toLocaleString("zh-CN")}</p>
          </Card>

          {/* FMEA Link Modal (inline) */}
          {linkModal && (
            <Card title="选择关联的 FMEA" size="small" style={{ marginTop: 16 }}>
              <Select
                showSearch
                style={{ width: "100%" }}
                placeholder="搜索 FMEA 文档"
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
                options={fmeas.map((f) => ({
                  value: f.fmea_id,
                  label: `${f.document_no} - ${f.title}`,
                }))}
                onChange={(val) => handleLinkFMEA(val)}
              />
              <Button style={{ marginTop: 8 }} onClick={() => setLinkModal(false)}>取消</Button>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 4: Update App.tsx CAPA routes**

In `frontend/src/App.tsx`:

```typescript
import CAPAListPage from "./pages/capa/CAPAListPage";
import CAPADetailPage from "./pages/capa/CAPADetailPage";

// Replace: <Route path="/capa" element={<div>CAPA List</div>} />
// With: <Route path="/capa" element={<CAPAListPage />} />
// Replace: <Route path="/capa/:id" element={<div>CAPA Detail</div>} />
// With: <Route path="/capa/:id" element={<CAPADetailPage />} />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/capa.ts frontend/src/pages/capa/ frontend/src/App.tsx
git commit -m "feat: add 8D/CAPA list and detail pages with step workflow"
```

---

## Phase 5: Integration & Final Assembly

### Task 18: Docker Compose Integration Test & Seed Data

**Files:**
- Create: `backend/app/seed.py`

- [ ] **Step 1: Write backend/app/seed.py**

```python
"""
Seed script: creates demo data for development.
Run: docker compose exec backend python -m app.seed
"""
import asyncio
from datetime import date, datetime, timezone
from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.core.security import hash_password


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "Process", "name": "SMT贴装", "process_number": "OP10"},
        {"id": "n2", "type": "Function", "name": "元件贴装"},
        {"id": "n3", "type": "FailureMode", "name": "元件偏移", "severity": 7, "occurrence": 4, "detection": 3},
        {"id": "n4", "type": "FailureCause", "name": "贴装压力不足"},
        {"id": "n5", "type": "ControlMeasure", "name": "定期校准贴片机"},
        {"id": "n6", "type": "Process", "name": "回流焊", "process_number": "OP20"},
        {"id": "n7", "type": "Function", "name": "焊接连接"},
        {"id": "n8", "type": "FailureMode", "name": "焊点虚焊", "severity": 8, "occurrence": 3, "detection": 5},
        {"id": "n9", "type": "FailureCause", "name": "回流温度不足"},
        {"id": "n10", "type": "ControlMeasure", "name": "炉温曲线监控"},
    ],
    "edges": [
        {"source": "n1", "target": "n2", "type": "HAS_FUNCTION"},
        {"source": "n2", "target": "n3", "type": "HAS_FAILURE_MODE"},
        {"source": "n3", "target": "n4", "type": "HAS_CAUSE"},
        {"source": "n4", "target": "n5", "type": "CONTROLLED_BY"},
        {"source": "n6", "target": "n7", "type": "HAS_FUNCTION"},
        {"source": "n7", "target": "n8", "type": "HAS_FAILURE_MODE"},
        {"source": "n8", "target": "n9", "type": "HAS_CAUSE"},
        {"source": "n9", "target": "n10", "type": "CONTROLLED_BY"},
    ],
}


async def seed():
    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(select(User).where(User.username == "engineer"))
        if result.scalar_one_or_none():
            print("Already seeded, skipping.")
            return

        # Users
        engineer = User(
            username="engineer", display_name="质量工程师",
            password_hash=hash_password("Engineer@2026"), role="quality_engineer",
        )
        manager = User(
            username="manager", display_name="质量经理",
            password_hash=hash_password("Manager@2026"), role="admin",
        )
        viewer = User(
            username="viewer", display_name="只读用户",
            password_hash=hash_password("Viewer@2026"), role="viewer",
        )
        db.add_all([engineer, manager, viewer])
        await db.flush()

        # FMEA
        fmea1 = FMEADocument(
            document_no="PFMEA-2026-001", title="SMT焊接工序PFMEA",
            fmea_type="PFMEA", status="approved",
            graph_data=SAMPLE_GRAPH,
            created_by=engineer.user_id, updated_by=engineer.user_id,
            approved_by=manager.user_id,
            approved_at=datetime.now(timezone.utc),
        )
        fmea2 = FMEADocument(
            document_no="PFMEA-2026-002", title="注塑工序PFMEA",
            fmea_type="PFMEA", status="draft",
            graph_data={"nodes": [], "edges": []},
            created_by=engineer.user_id, updated_by=engineer.user_id,
        )
        db.add_all([fmea1, fmea2])
        await db.flush()

        # CAPA
        capa1 = CAPAEightD(
            document_no="8D-2026-001", title="焊接不良客诉",
            status="D4_ROOT_CAUSE", severity="严重",
            d1_team=[{"name": "张三", "role": "质量工程师"}, {"name": "李四", "role": "工艺工程师"}],
            d2_description="客户反馈PCB组件焊接不良，影响数量500pcs",
            d3_interim="已隔离不良批次，100%加检",
            d4_root_cause="初步判断为回流焊温度曲线异常",
            due_date=date(2026, 6, 1),
            fmea_ref_id=fmea1.fmea_id,
            created_by=engineer.user_id,
        )
        capa2 = CAPAEightD(
            document_no="8D-2026-002", title="注塑尺寸超差",
            status="D1_TEAM", severity="一般",
            d1_team=[],
            due_date=date(2026, 6, 15),
            created_by=engineer.user_id,
        )
        db.add_all([capa1, capa2])
        await db.commit()

    print("Seed data created successfully!")
    print("Users: admin/Admin@2026, engineer/Engineer@2026, manager/Manager@2026")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Start Docker Compose and run migrations + seed**

```bash
docker compose up -d db redis

# Wait for PostgreSQL
until docker compose exec db pg_isready -U qms; do sleep 1; done

# Run migrations
cd backend && alembic upgrade head

# Seed data
docker compose exec backend python -m app.seed

# Start full stack
docker compose up -d
```

- [ ] **Step 3: Verify the full stack**

```bash
# Test backend health
curl http://localhost:8000/api/health

# Test login
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@2026"}'

# Test frontend
curl http://localhost:5173 | head -5
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed.py
git commit -m "feat: add seed data script and integration test steps"
```

---

## Implementation Order

1. **Task 1** — Docker Compose & project root
2. **Task 2** — Backend scaffold (FastAPI)
3. **Task 3** — Frontend scaffold (React + Vite)
4. **Task 4** — User ORM model & migration
5. **Task 5** — Auth core (JWT + password hashing)
6. **Task 6** — Auth API (login, register, me)
7. **Task 7** — FMEA & CAPA ORM models
8. **Task 8** — State machines
9. **Task 9** — FMEA service & API
10. **Task 10** — 8D/CAPA service & API
11. **Task 11** — Dashboard API
12. **Task 12** — Frontend types, API client, auth store
13. **Task 13** — App layout, login page, auth guard
14. **Task 14** — Dashboard page
15. **Task 15** — FMEA list page
16. **Task 16** — FMEA editor page
17. **Task 17** — 8D/CAPA list & detail pages
18. **Task 18** — Seed data & integration test

---
