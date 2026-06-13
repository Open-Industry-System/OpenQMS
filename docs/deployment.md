# 部署指南

本文档介绍如何部署 OpenQMS，包括 Docker Compose（推荐）和本地开发环境两种方式。

---

## 1. Docker Compose 部署（推荐）

### 1.1 前提条件

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Docker | 20.10+ | 容器运行时 |
| Docker Compose | v2.0+ | 服务编排 |
| 可用内存 | 4 GB+ | PostgreSQL + Neo4j + Ollama 各需 256–512 MB |

### 1.2 配置

项目根目录提供 `.env.example`，生产环境请复制并修改：

```bash
cp .env.example .env
```

关键环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://qms:qms_dev_2026@db:5432/qms` | 数据库连接（Docker 内部） |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 连接 |
| `SECRET_KEY` | `openqms-local-dev-2026-jwt-signing-key` | **JWT 签名密钥，生产环境必须修改** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | Token 过期时间（分钟） |

> ⚠️ `SECRET_KEY` 在生产环境必须替换为随机长字符串，否则存在安全风险。

### 1.3 启动服务

```bash
docker compose up -d
```

首次启动会自动构建前后端镜像。查看服务状态：

```bash
docker compose ps
```

等待 `db` 和 `neo4j` 容器变为 `healthy`（约 15–30 秒）。

### 1.4 初始化数据库

```bash
# 运行数据库迁移
docker compose exec backend alembic upgrade head

# 导入演示数据（含用户、FMEA、CAPA、供应商等）
docker compose exec backend python -m app.seed
```

### 1.5 访问

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000/api |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Neo4j Browser | http://localhost:7474 |

### 1.6 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `Admin@2026` | 系统管理员 |
| `engineer` | `Engineer@2026` | 现场质量工程师 |
| `manager` | `Manager@2026` | 质量经理 |
| `viewer` | `Viewer@2026` | 只读用户 |
| `groupadmin` | `GroupAdmin@2026` | 系统管理员（集团） |

> ⚠️ 生产环境请务必修改默认密码。

### 1.7 停止与重启

```bash
# 停止所有服务
docker compose down

# 停止并删除数据卷（重置数据库）
docker compose down -v

# 重启单个服务
docker compose restart backend
```

---

## 2. 本地开发环境

### 2.1 前提条件

| 依赖 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 15+ |
| Redis | 7+ |

### 2.2 后端

```bash
cd backend
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example .env
# 编辑 .env 中的 DATABASE_URL 和 REDIS_URL 指向本地服务

# 数据库迁移
alembic upgrade head

# 导入演示数据
python -m app.seed

# 启动开发服务器
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2.3 前端

```bash
cd frontend
npm install

# 启动开发服务器（自动代理 /api → localhost:8000）
npm run dev
```

前端默认运行在 `http://localhost:5173`，通过 Vite 代理将 `/api` 请求转发到后端。

### 2.4 环境变量

本地开发时，后端读取项目根目录或 `backend/` 目录下的 `.env` 文件：

```env
DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=120
```

---

## 3. 数据库迁移

Alembic 管理所有数据库 schema 变更。

```bash
# 应用所有待执行的迁移
alembic upgrade head

# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 回退一个版本
alembic downgrade -1
```

> ⚠️ 迁移文件为手写（非自动生成），请勿使用 `alembic revision --autogenerate` 覆盖现有迁移。

---

## 4. 常见问题

### 4.1 数据库连接失败

```
sqlalchemy.exc.OperationalError: connection refused
```

- 检查 PostgreSQL 是否运行：`docker compose ps db`
- 检查 `DATABASE_URL` 中的主机名是否正确（Docker 内用 `db`，本地用 `localhost`）
- 确认 `qms` 数据库已创建

### 4.2 前端代理 404

- 确认后端运行在 `localhost:8000`
- 检查 `frontend/vite.config.ts` 中的 proxy 配置
- Docker 环境下前端通过 `BACKEND_URL` 环境变量指向后端

### 4.3 Neo4j 连接失败

- 检查 Neo4j 容器是否 `healthy`：`docker compose ps neo4j`
- 知识图谱功能依赖 Neo4j，如不需要可忽略该错误
- 浏览器访问 `http://localhost:7474` 验证 Neo4j Browser 可用

### 4.4 种子数据报错 "Already seeded"

表示数据库已有种子数据，跳过即可。如需重置：

```bash
docker compose down -v    # 删除数据卷
docker compose up -d      # 重新启动
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

### 4.5 Ollama 内存不足

Ollama 容器默认限制 2 GB 内存。如需运行大模型，调整 `docker-compose.yml` 中 `ollama` 服务的 `memory` 限制，或禁用 AI 推荐功能。