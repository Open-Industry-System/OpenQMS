# FMEA 智能推荐升级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前端规则引擎升级为后端编排的混合推荐系统（规则 + LLM），用户输入时自动触发，以内联下拉展示建议。

**Architecture:** 后端 RecommendationService 编排规则引擎和可选 LLM provider，通过 PostgreSQL 缓存结果。前端 SmartSuggestionDropdown 组件集成到 FMEA 编辑器单元格，500ms 防抖自动触发。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) | React 18 + TypeScript + Ant Design 5 | PostgreSQL 15

**Design Spec:** `docs/superpowers/specs/2026-06-01-fmea-smart-recommend-design.md`

---

## 文件结构总览

### 后端新增

| 文件 | 职责 |
|------|------|
| `backend/app/schemas/recommendation.py` | 请求/响应 Pydantic 模型 |
| `backend/app/models/recommendation_cache.py` | 缓存 ORM 模型（共享 `app.database.Base`） |
| `backend/app/services/llm_provider.py` | LLM 多提供商抽象 + 工厂 |
| `backend/app/services/recommendation_service.py` | 推荐服务核心（规则 + LLM + 缓存） |
| `backend/alembic/versions/20260601_add_recommendation_cache.py` | 缓存表迁移 |

### 后端修改

| 文件 | 变更 |
|------|------|
| `backend/app/config.py` | 新增 LLM 相关配置字段 |
| `backend/app/api/fmea.py` | 实现 `/recommend` 端点（替换 501 stub） |
| `backend/app/main.py` | lifespan 中初始化 LLM provider |
| `backend/requirements.txt` | 新增 `anthropic`、`openai` 依赖 |

### 前端新增

| 文件 | 职责 |
|------|------|
| `frontend/src/api/recommendation.ts` | API 调用函数 |
| `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` | 智能建议下拉组件 |

### 前端修改

| 文件 | 变更 |
|------|------|
| `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` | 集成 SmartSuggestionDropdown 到 6 列 |

---

## Task 1: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/recommendation.py`

- [ ] **Step 1: 创建推荐请求/响应 schema 文件**

```python
# backend/app/schemas/recommendation.py
import uuid
from typing import Literal
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization"
    ]
    context: dict = Field(default_factory=dict)


class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "llm"] = "rule"
    explanation: str = ""


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "hybrid", "rule_fallback"]
    cached: bool = False
    llm_available: bool = False


class SuggestionList(BaseModel):
    """LLM 输出校验模型。"""
    suggestions: list[SuggestionItem]
```

- [ ] **Step 2: 验证 schema 可导入**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.schemas.recommendation import RecommendRequest, RecommendResponse, SuggestionItem; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/recommendation.py
git commit -m "feat(rec): add recommendation request/response Pydantic schemas"
```

---

## Task 2: Alembic Migration — recommendation_cache 表

**Files:**
- Create: `backend/alembic/versions/20260601_add_recommendation_cache.py`

- [ ] **Step 1: 创建迁移文件**

```python
"""add recommendation_cache table

Revision ID: 20260601_rec_cache
Revises: 028_permission_matrix
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260601_rec_cache"
down_revision = "028_permission_matrix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_cache",
        sa.Column("cache_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fmea_id", UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("fmea_type", sa.String(20), nullable=False),
        sa.Column("suggestions", JSONB, nullable=False),
        sa.Column("source", sa.String(15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), server_default=sa.text("now() + INTERVAL '24 hours'"), nullable=False),
        sa.UniqueConstraint("fmea_id", "trigger_type", "context_hash", name="uq_recommendation_cache_lookup"),
    )
    op.create_index("ix_recommendation_cache_lookup", "recommendation_cache", ["fmea_id", "trigger_type", "context_hash", "expires_at"])
    op.create_index("ix_recommendation_cache_expires", "recommendation_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_table("recommendation_cache")
```

- [ ] **Step 2: 验证迁移文件语法**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "import alembic.config; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/20260601_add_recommendation_cache.py
git commit -m "feat(rec): add recommendation_cache table migration"
```

---

## Task 2b: RecommendationCache ORM 模型

**Files:**
- Create: `backend/app/models/recommendation_cache.py`

- [ ] **Step 1: 创建 ORM 模型文件**

使用项目共享的 `app.database.Base`，与其他模型（`FMEADocument`、`User`）保持一致：

```python
# backend/app/models/recommendation_cache.py
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecommendationCache(Base):
    __tablename__ = "recommendation_cache"
    __table_args__ = (
        UniqueConstraint("fmea_id", "trigger_type", "context_hash", name="uq_recommendation_cache_lookup"),
    )

    cache_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fmea_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    fmea_type: Mapped[str] = mapped_column(String(20), nullable=False)
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(15), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 2: 验证模型可导入**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models.recommendation_cache import RecommendationCache; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/recommendation_cache.py
git commit -m "feat(rec): add RecommendationCache ORM model"
```

---

## Task 3: LLM Settings 配置

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 在 Settings 类中添加 LLM 配置字段**

在 `backend/app/config.py` 的 `Settings` 类末尾（`GRAPH_REPOSITORY` 之后）添加：

```python
    # LLM 推荐（可选，未设置则纯规则引擎模式）
    LLM_PROVIDER: str = ""       # claude | openai | local | 留空=纯规则
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""          # 各 provider 有内部默认值
    LLM_BASE_URL: str = ""       # 仅 local 模式
    LLM_TIMEOUT: int = 5         # 超时秒数
```

- [ ] **Step 2: 验证配置可加载**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.config import settings; print(settings.LLM_PROVIDER); print('OK')"`
Expected: 空字符串（默认值）后跟 `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(rec): add LLM provider settings to config"
```

---

## Task 4: LLM Provider 抽象

**Files:**
- Create: `backend/app/services/llm_provider.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加依赖到 requirements.txt**

在 `backend/requirements.txt` 末尾添加：

```
anthropic>=0.40.0
openai>=1.50.0
```

注意：`httpx==0.27.2` 已存在，无需重复添加。

- [ ] **Step 2: 创建 LLM provider 文件**

```python
# backend/app/services/llm_provider.py
import json
import logging
from typing import Protocol, Any

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 10_240  # 10KB


class LLMProvider(Protocol):
    async def complete(self, prompt: str, response_schema: dict) -> dict: ...


class ClaudeProvider:
    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return json.loads(text)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return json.loads(text)


class LocalProvider:
    def __init__(self, base_url: str, model: str):
        import httpx
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30)

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        response = await self.client.post(
            "/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        text = response.json().get("response", "")
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return json.loads(text)


def create_llm_provider() -> LLMProvider | None:
    """工厂函数：根据环境变量创建 provider，未配置时返回 None。"""
    provider_name = settings.LLM_PROVIDER
    if not provider_name:
        return None

    api_key = settings.LLM_API_KEY
    if not api_key and provider_name != "local":
        logger.warning("LLM_PROVIDER=%s requires LLM_API_KEY, falling back to rule-only mode", provider_name)
        return None

    model = settings.LLM_MODEL

    try:
        if provider_name == "claude":
            return ClaudeProvider(api_key=api_key, model=model or "claude-sonnet-4-6-20250514")
        elif provider_name == "openai":
            return OpenAIProvider(api_key=api_key, model=model or "gpt-4o")
        elif provider_name == "local":
            base_url = settings.LLM_BASE_URL
            if not base_url:
                logger.warning("LLM_PROVIDER=local requires LLM_BASE_URL, falling back to rule-only mode")
                return None
            if not model:
                logger.warning("LLM_PROVIDER=local requires LLM_MODEL, falling back to rule-only mode")
                return None
            return LocalProvider(base_url=base_url, model=model)
        else:
            logger.warning("Unknown LLM_PROVIDER: %s, falling back to rule-only mode", provider_name)
            return None
    except ImportError as e:
        logger.warning("LLM provider import failed (%s), falling back to rule-only mode: %s", provider_name, e)
        return None
```

- [ ] **Step 3: 验证可导入**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.services.llm_provider import create_llm_provider; p = create_llm_provider(); print(f'provider={p}'); print('OK')"`
Expected: `provider=None`（未配置 LLM）后跟 `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/llm_provider.py backend/requirements.txt
git commit -m "feat(rec): add LLM provider abstraction with Claude/OpenAI/Local support"
```

---

## Task 5: 规则引擎（从前端迁移）

**Files:**
- Create: `backend/app/services/recommendation_service.py`（本 Task 只写规则引擎部分）

- [ ] **Step 1: 创建 recommendation_service.py 规则引擎部分**

将 `frontend/src/utils/dfmeaRules.ts` 的逻辑迁移到 Python。文件包含规则引擎 + 占位的 RecommendationService 类（后续 Task 补全）。

```python
# backend/app/services/recommendation_service.py
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule Engine (migrated from frontend/src/utils/dfmeaRules.ts)
# ---------------------------------------------------------------------------

@dataclass
class RuleSuggestion:
    name: str
    confidence: float = 0.7
    source: Literal["rule"] = "rule"
    explanation: str = ""


@dataclass
class RuleResult:
    suggestions: list[RuleSuggestion] = field(default_factory=list)
    quality: Literal["specific", "generic"] = "specific"


# 1. Failure-mode generation from Chinese function description
VERB_PATTERNS: dict[str, list[str]] = {
    "采集": ["无法采集", "采集失效", "采集精度不足", "采集延迟"],
    "收集": ["无法收集", "收集失效", "收集不完整", "收集延迟"],
    "获取": ["无法获取", "获取失效", "获取不完整", "获取延迟"],
    "传输": ["无法传输", "传输失效", "传输失真", "传输延迟"],
    "发送": ["无法发送", "发送失效", "发送失真", "发送延迟"],
    "传递": ["无法传递", "传递失效", "传递失真", "传递延迟"],
    "控制": ["无法控制", "控制失效", "控制精度不足", "控制响应慢"],
    "调节": ["无法调节", "调节失效", "调节精度不足", "调节响应慢"],
    "调控": ["无法调控", "调控失效", "调控精度不足", "调控响应慢"],
    "检测": ["无法检测", "检测失效", "检测精度不足", "误检测"],
    "监测": ["无法监测", "监测失效", "监测精度不足", "误监测"],
    "识别": ["无法识别", "识别失效", "识别精度不足", "误识别"],
    "保护": ["保护失效", "无法保护", "保护不足", "保护误动作"],
    "防护": ["防护失效", "无法防护", "防护不足", "防护误动作"],
    "隔离": ["隔离失效", "无法隔离", "隔离不足", "隔离误动作"],
    "显示": ["无法显示", "显示失效", "显示错误", "显示延迟"],
    "指示": ["无法指示", "指示失效", "指示错误", "指示延迟"],
    "反馈": ["无法反馈", "反馈失效", "反馈错误", "反馈延迟"],
    "存储": ["无法存储", "存储失效", "存储丢失", "存储容量不足"],
    "保存": ["无法保存", "保存失效", "保存丢失", "保存容量不足"],
    "记录": ["无法记录", "记录失效", "记录丢失", "记录容量不足"],
    "供电": ["无法供电", "供电失效", "供电不足", "供电不稳定"],
    "供能": ["无法供能", "供能失效", "供能不足", "供能不稳定"],
    "驱动": ["无法驱动", "驱动失效", "驱动力不足", "驱动不稳定"],
    "连接": ["连接失效", "无法连接", "连接松动", "接触不良"],
    "接合": ["接合失效", "无法接合", "接合松动", "接合不良"],
    "固定": ["固定失效", "无法固定", "固定松动", "固定不良"],
    "密封": ["密封失效", "无法密封", "密封不良", "泄漏"],
    "封闭": ["封闭失效", "无法封闭", "封闭不良", "泄漏"],
}

# 2. Failure-chain suggestions (effects + causes)
FAILURE_CHAIN_MAP: dict[str, dict[str, list[str]]] = {
    "无法采集": {
        "effects": ["系统数据缺失", "控制决策错误", "功能降级"],
        "causes": ["传感器故障", "信号干扰", "线路断路", "接口氧化"],
    },
    "采集精度不足": {
        "effects": ["控制偏差", "系统性能下降", "误报警"],
        "causes": ["传感器老化", "校准漂移", "温度影响", "电磁干扰"],
    },
    "无法控制": {
        "effects": ["系统失控", "设备损坏", "安全风险"],
        "causes": ["执行器故障", "控制算法缺陷", "反馈信号丢失", "电源异常"],
    },
    "密封失效": {
        "effects": ["介质泄漏", "环境污染", "设备腐蚀", "安全风险"],
        "causes": ["密封件老化", "安装不当", "材料选型错误", "温度超限"],
    },
    "连接失效": {
        "effects": ["电路断开", "信号中断", "功能丧失", "系统停机"],
        "causes": ["接触不良", "焊接缺陷", "振动疲劳", "腐蚀"],
    },
}

DEFAULT_EFFECTS = ["功能降级", "系统性能下降"]
DEFAULT_CAUSES = ["零部件老化", "环境因素", "制造缺陷"]

GENERIC_PLACEHOLDERS = {"功能降级", "系统性能下降", "零部件老化", "环境因素", "制造缺陷"}


class RuleEngine:
    """FMEA 推荐规则引擎，从前端 dfmeaRules.ts 迁移。"""

    def evaluate(self, trigger_type: str, context: dict) -> RuleResult:
        dispatch = {
            "failure_mode": self._generate_failure_modes,
            "failure_effect": self._suggest_failure_effect,
            "failure_cause": self._suggest_failure_cause,
            "measure": self._suggest_measures,
            "optimization": self._suggest_optimization,
        }
        handler = dispatch.get(trigger_type)
        if not handler:
            return RuleResult(suggestions=[], quality="generic")
        return handler(context)

    def _generate_failure_modes(self, context: dict) -> RuleResult:
        func_desc = context.get("function_description", "")
        if not func_desc:
            return RuleResult(suggestions=[], quality="generic")

        for verb, modes in VERB_PATTERNS.items():
            if verb in func_desc:
                return RuleResult(
                    suggestions=[RuleSuggestion(name=m, confidence=0.7, explanation=f"动词「{verb}」匹配") for m in modes],
                    quality="specific",
                )

        # Fallback: generic negations
        fallback = [
            f"{func_desc}失效", f"无法{func_desc}", f"{func_desc}精度不足", f"{func_desc}延迟"
        ]
        return RuleResult(
            suggestions=[RuleSuggestion(name=m, confidence=0.4, explanation="通用否定模式") for m in fallback],
            quality="generic",
        )

    def _suggest_failure_effect(self, context: dict) -> RuleResult:
        fm = context.get("failure_mode", "")
        for key, chain in FAILURE_CHAIN_MAP.items():
            if key in fm:
                return RuleResult(
                    suggestions=[RuleSuggestion(name=e, confidence=0.7, explanation=f"关联失效模式「{key}」") for e in chain["effects"]],
                    quality="specific",
                )
        return RuleResult(
            suggestions=[RuleSuggestion(name=e, confidence=0.3, explanation="通用默认") for e in DEFAULT_EFFECTS],
            quality="generic",
        )

    def _suggest_failure_cause(self, context: dict) -> RuleResult:
        fm = context.get("failure_mode", "")
        for key, chain in FAILURE_CHAIN_MAP.items():
            if key in fm:
                return RuleResult(
                    suggestions=[RuleSuggestion(name=c, confidence=0.7, explanation=f"关联失效模式「{key}」") for c in chain["causes"]],
                    quality="specific",
                )
        return RuleResult(
            suggestions=[RuleSuggestion(name=c, confidence=0.3, explanation="通用默认") for c in DEFAULT_CAUSES],
            quality="generic",
        )

    def _suggest_measures(self, context: dict) -> RuleResult:
        fm = context.get("failure_mode", "")
        ap = context.get("ap", "L")
        prevention: list[str] = []
        detection: list[str] = []

        if ap == "H":
            prevention.extend(["冗余设计（双通道/备份）", "选用更高可靠性等级元器件", "降额设计", "失效安全设计"])
            detection.extend(["在线实时监测", "自诊断功能", "出厂100%功能测试"])
        elif ap == "M":
            prevention.extend(["优化设计参数", "增加防错结构", "选用成熟工艺"])
            detection.extend(["定期功能测试", "过程巡检", "来料检验"])
        else:
            prevention.extend(["标准化设计", "选用合格供应商物料"])
            detection.extend(["常规检验", "用户反馈跟踪"])

        import re
        if re.search(r"采集|检测|监测|识别", fm):
            prevention.extend(["传感器冗余布置", "信号滤波设计"])
            detection.extend(["传感器信号校验", "标定周期缩短"])
        if re.search(r"密封|封闭|泄漏", fm):
            prevention.extend(["双重密封结构", "密封槽优化设计"])
            detection.extend(["气密性测试", "泄漏监测"])
        if re.search(r"连接|接合|固定|接触", fm):
            prevention.extend(["防松结构设计", "镀金/镀银处理"])
            detection.extend(["接触电阻测试", "振动试验验证"])

        suggestions = (
            [RuleSuggestion(name=p, confidence=0.6, explanation="预防措施") for p in prevention]
            + [RuleSuggestion(name=d, confidence=0.6, explanation="检测措施") for d in detection]
        )
        quality: Literal["specific", "generic"] = "specific" if (fm and any(kw in fm for kw in ["采集", "密封", "连接"])) else "generic"
        return RuleResult(suggestions=suggestions, quality=quality)

    def _suggest_optimization(self, context: dict) -> RuleResult:
        s = context.get("severity", 0)
        o = context.get("occurrence", 0)
        d = context.get("detection", 0)
        ap = context.get("ap", "")

        if not ap and s and o and d:
            # Compute AP if not provided
            from app.state_machines.fmea_state import compute_ap
            ap = compute_ap(s, o, d)

        hints: list[str] = []
        if ap == "H":
            hints = ["必须采取优化措施", "建议设计变更以降低S或O", "增加冗余或提高检测能力"]
        elif ap == "M":
            hints = ["建议采取优化措施", "重点改进探测手段或降低发生度"]
        else:
            hints = ["当前风险可接受", "保持现有控制措施，持续监控"]

        return RuleResult(
            suggestions=[RuleSuggestion(name=h, confidence=0.6, explanation=f"AP={ap}") for h in hints],
            quality="specific" if ap in ("H", "M") else "generic",
        )
```

- [ ] **Step 2: 验证规则引擎可导入和基本功能**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "
from app.services.recommendation_service import RuleEngine
engine = RuleEngine()
r = engine.evaluate('failure_mode', {'function_description': '密封腔体'})
print(f'suggestions={[s.name for s in r.suggestions]}, quality={r.quality}')
assert len(r.suggestions) == 4
assert r.quality == 'specific'
print('OK')
"`
Expected: `suggestions=['密封失效', '无法密封', '密封不良', '泄漏'], quality=specific` 后跟 `OK`

- [ ] **Step 3: 验证 generic 回退路径**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "
from app.services.recommendation_service import RuleEngine
engine = RuleEngine()
r = engine.evaluate('failure_mode', {'function_description': '传递信号'})
print(f'suggestions={[s.name for s in r.suggestions]}, quality={r.quality}')
assert r.quality == 'specific'
r2 = engine.evaluate('failure_mode', {'function_description': '抬升物体'})
print(f'fallback={[s.name for s in r2.suggestions]}, quality={r2.quality}')
assert r2.quality == 'generic'
print('OK')
"`
Expected: `quality=generic` for fallback, 后跟 `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/recommendation_service.py
git commit -m "feat(rec): add rule engine migrated from frontend dfmeaRules.ts"
```

---

## Task 6: RecommendationService 核心（缓存 + LLM 编排）

**Files:**
- Modify: `backend/app/services/recommendation_service.py`

- [ ] **Step 1: 在 recommendation_service.py 中添加缓存模型和 RecommendationService 类**

在文件末尾追加：

```python
# ---------------------------------------------------------------------------
# Recommendation Service
# ---------------------------------------------------------------------------
import asyncio
import uuid as _uuid
from sqlalchemy import select, delete, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.fmea import FMEADocument
from app.models.recommendation_cache import RecommendationCache
from app.schemas.recommendation import (
    RecommendRequest, RecommendResponse, SuggestionItem, SuggestionList,
)
from app.services.llm_provider import LLMProvider


PROMPT_TEMPLATES = {
    "failure_mode": """你是一位资深质量工程师，精通 AIAG-VDA FMEA 方法论。

当前上下文：
- FMEA 类型: {fmea_type}
- 产品线: {product_line}
- 工艺步骤: {process_step}
- 功能描述: {function_description}

历史相似 FMEA 中的失败模式：
{historical_patterns}

请根据以上信息，推荐 3-5 个可能的失败模式。
要求：
1. 具体、可操作，不要泛泛而谈
2. 与当前工艺/功能直接相关
3. 参考历史数据中的真实案例

返回 JSON 格式：
{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}
""",
    "failure_effect": """你是一位资深质量工程师。当前失效模式：{failure_mode}。
请推荐 3-5 个可能的失效效应。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
    "failure_cause": """你是一位资深质量工程师。当前失效模式：{failure_mode}。
请推荐 3-5 个可能的失效原因。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
    "measure": """你是一位资深质量工程师。当前失效模式：{failure_mode}，AP={ap}。
请推荐预防措施和检测措施。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
    "optimization": """你是一位资深质量工程师。失效模式：{failure_mode}，S={severity} O={occurrence} D={detection}。
请推荐优化行动。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
}


class RecommendationService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider | None):
        self.db = db
        self.llm = llm_provider
        self.rules = RuleEngine()

    async def recommend(self, fmea_id: _uuid.UUID, request: RecommendRequest) -> RecommendResponse:
        fmea = await self._get_fmea_or_404(fmea_id)

        # 1. Check cache
        context_hash = self._compute_context_hash(request.context)
        cached = await self._get_cached(fmea_id, request.trigger_type, context_hash)
        if cached:
            return cached

        # 2. Rule engine
        rule_result = self.rules.evaluate(request.trigger_type, request.context)

        # 3. LLM if generic + available
        if rule_result.quality == "generic" and self.llm is not None:
            try:
                llm_context = await self._assemble_context(fmea, request)
                prompt = self._build_prompt(request.trigger_type, llm_context)
                llm_result = await asyncio.wait_for(
                    self.llm.complete(prompt, {}),
                    timeout=settings.LLM_TIMEOUT,
                )
                validated = SuggestionList.model_validate(llm_result)
                suggestions = self._merge_suggestions(rule_result.suggestions, validated.suggestions)
                source = "hybrid"
            except (asyncio.TimeoutError, Exception) as e:
                suggestions = [SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation) for s in rule_result.suggestions]
                source = "rule_fallback"
                logger.warning("LLM failed, falling back to rules: %s", e)
        else:
            suggestions = [SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation) for s in rule_result.suggestions]
            source = "rule"

        response = RecommendResponse(
            suggestions=suggestions,
            source=source,
            cached=False,
            llm_available=self.llm is not None,
        )
        await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response)
        return response

    # -- Helpers --

    async def _get_fmea_or_404(self, fmea_id: _uuid.UUID) -> FMEADocument:
        from fastapi import HTTPException
        stmt = select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
        result = await self.db.execute(stmt)
        fmea = result.scalar_one_or_none()
        if not fmea:
            raise HTTPException(status_code=404, detail="FMEA not found")
        return fmea

    def _compute_context_hash(self, context: dict) -> str:
        raw = json.dumps(context, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _get_cached(self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str) -> RecommendResponse | None:
        stmt = (
            select(RecommendationCache)
            .where(RecommendationCache.fmea_id == fmea_id)
            .where(RecommendationCache.trigger_type == trigger_type)
            .where(RecommendationCache.context_hash == context_hash)
            .where(RecommendationCache.expires_at > func.now())
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            return RecommendResponse(
                suggestions=row.suggestions,
                source=row.source,
                cached=True,
                llm_available=self.llm is not None,
            )
        return None

    async def _cache_result(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str,
        fmea: FMEADocument, response: RecommendResponse,
    ) -> None:
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                fmea_id=fmea_id,
                trigger_type=trigger_type,
                context_hash=context_hash,
                product_line_code=fmea.product_line_code,
                fmea_type=fmea.fmea_type,
                suggestions=[s.model_dump() for s in response.suggestions],
                source=response.source,
            )
            .on_conflict_do_update(
                index_elements=["fmea_id", "trigger_type", "context_hash"],
                set_={
                    "suggestions": [s.model_dump() for s in response.suggestions],
                    "source": response.source,
                    "product_line_code": fmea.product_line_code,
                    "fmea_type": fmea.fmea_type,
                    "created_at": func.now(),
                    "expires_at": func.now() + text("INTERVAL '24 hours'"),
                },
            )
        )
        await self.db.execute(stmt)

    async def invalidate_cache_for_fmea(self, fmea_id: _uuid.UUID) -> None:
        await self.db.execute(
            delete(RecommendationCache).where(RecommendationCache.fmea_id == fmea_id)
        )

    async def _assemble_context(self, fmea: FMEADocument, request: RecommendRequest) -> dict:
        historical = await self._get_similar_fmeas(fmea)
        return {
            "fmea_type": fmea.fmea_type,
            "product_line": fmea.product_line_code,
            "current_context": request.context,
            "historical_patterns": self._extract_patterns(historical),
        }

    async def _get_similar_fmeas(self, fmea: FMEADocument, limit: int = 5) -> list[FMEADocument]:
        stmt = (
            select(FMEADocument)
            .where(FMEADocument.fmea_type == fmea.fmea_type)
            .where(FMEADocument.product_line_code == fmea.product_line_code)
            .where(FMEADocument.status == "approved")
            .where(FMEADocument.fmea_id != fmea.fmea_id)
            .order_by(FMEADocument.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _extract_patterns(self, fmeas: list[FMEADocument]) -> list[dict]:
        patterns = []
        for fmea in fmeas:
            nodes = fmea.graph_data.get("nodes", [])
            edges = fmea.graph_data.get("edges", [])
            for node in nodes:
                if node.get("type") == "FailureMode":
                    effects = [n["name"] for n in nodes if n["type"] == "FailureEffect"
                               and any(e["source"] == node["id"] and e["target"] == n["id"] for e in edges if e["type"] == "EFFECT_OF")]
                    causes = [n["name"] for n in nodes if n["type"] == "FailureCause"
                              and any(e["source"] == n["id"] and e["target"] == node["id"] for e in edges if e["type"] == "CAUSE_OF")]
                    patterns.append({"failure_mode": node["name"], "effects": effects, "causes": causes, "source_doc": fmea.document_no})
        return patterns

    def _build_prompt(self, trigger_type: str, context: dict) -> str:
        template = PROMPT_TEMPLATES.get(trigger_type, "")
        safe = {k: v for k, v in context.get("current_context", {}).items()}
        safe.update({k: v for k, v in context.items() if k != "current_context"})
        safe["historical_patterns"] = json.dumps(context.get("historical_patterns", []), ensure_ascii=False)
        try:
            return template.format(**safe)
        except KeyError:
            return template

    def _merge_suggestions(self, rule_suggestions: list[RuleSuggestion], llm_suggestions: list[SuggestionItem]) -> list[SuggestionItem]:
        seen = {s.name for s in rule_suggestions}
        merged = [SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation) for s in rule_suggestions]
        for s in llm_suggestions:
            if s.name not in seen:
                merged.append(SuggestionItem(name=s.name, confidence=s.confidence, source="llm", explanation=s.explanation))
                seen.add(s.name)
        return merged
```

- [ ] **Step 2: 验证完整服务可导入**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.services.recommendation_service import RecommendationService, RuleEngine; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendation_service.py
git commit -m "feat(rec): add RecommendationService with cache, LLM orchestration, historical data"
```

---

## Task 7: API 端点 + 限流

**Files:**
- Modify: `backend/app/api/fmea.py`

- [ ] **Step 1: 在 fmea.py 中实现 /recommend 端点**

首先在文件顶部的 fastapi import 中添加 `Request`：
```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request
```

然后找到现有的 501 stub（约在文件末尾）：

```python
@router.post("/{fmea_id}/recommend")
async def recommend(fmea_id: uuid.UUID):
    raise HTTPException(status_code=501, detail="历史数据推荐功能将在 Phase 3 实现")
```

替换为：

```python
import time
from collections import defaultdict
from app.schemas.recommendation import RecommendRequest, RecommendResponse
from app.services.recommendation_service import RecommendationService

# Simple in-memory rate limiter
_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMITS = {"per_user": (5, 1.0), "per_fmea": (20, 1.0)}

def _check_rate_limit(key: str, limit: tuple[int, float]) -> bool:
    """Returns True if allowed, False if rate limited."""
    now = time.time()
    window = limit[1]
    max_req = limit[0]
    entries = _rate_store[key]
    # Prune old entries
    _rate_store[key] = [t for t in entries if now - t < window]
    if len(_rate_store[key]) >= max_req:
        return False
    _rate_store[key].append(now)
    return True


@router.post("/{fmea_id}/recommend", response_model=RecommendResponse)
async def recommend(
    fmea_id: uuid.UUID,
    request: RecommendRequest,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
):
    # Rate limiting
    user_key = f"rec_user:{user.user_id}"
    fmea_key = f"rec_fmea:{fmea_id}"
    if not _check_rate_limit(user_key, _RATE_LIMITS["per_user"]):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    if not _check_rate_limit(fmea_key, _RATE_LIMITS["per_fmea"]):
        raise HTTPException(status_code=429, detail="该文档请求过于频繁，请稍后重试")

    # Load FMEA for product-line access check
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

    # Validate minimum context
    if len(request.context.get("function_description", request.context.get("failure_mode", ""))) < 2:
        return RecommendResponse(suggestions=[], source="rule", cached=False, llm_available=False)

    # Use singleton LLM provider from app.state (initialized in lifespan)
    llm = getattr(fastapi_request.app.state, "llm_provider", None)
    service = RecommendationService(db=db, llm_provider=llm)
    return await service.recommend(fmea_id, request)
```

- [ ] **Step 2: 验证 API 文件语法**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.api.fmea import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/fmea.py
git commit -m "feat(rec): implement /recommend endpoint with rate limiting and permission check"
```

---

## Task 8: Wiring — main.py lifespan

**Files:**
- Modify: `backend/app/main.py`

**说明：** Task 7 的 `/recommend` 端点通过 `request.app.state.llm_provider` 获取 LLM provider 单例。本 Task 负责在 lifespan 中初始化该单例。

- [ ] **Step 1: 在 lifespan 中初始化 LLM provider 并存入 app.state**

在 `backend/app/main.py` 的 `lifespan` 函数中，在数据库初始化之后（`async with async_session() as db:` 块之后、`yield` 之前）添加：

```python
    # Initialize LLM provider (non-fatal)
    from app.services.llm_provider import create_llm_provider
    import logging as _logging
    try:
        app.state.llm_provider = create_llm_provider()
    except Exception as e:
        _logging.getLogger(__name__).warning("LLM provider init failed: %s", e)
        app.state.llm_provider = None
```

- [ ] **Step 2: 验证 main.py 语法**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(rec): initialize LLM provider singleton in app lifespan"
```

---

## Task 9: 前端 API Client

**Files:**
- Create: `frontend/src/api/recommendation.ts`

- [ ] **Step 1: 创建前端 API 调用文件**

```typescript
// frontend/src/api/recommendation.ts
import client from "./client";

export interface Suggestion {
  name: string;
  confidence: number;
  source: "rule" | "llm";
  explanation: string;
}

export interface RecommendRequest {
  trigger_type: string;
  context: Record<string, unknown>;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: "rule" | "hybrid" | "rule_fallback";
  cached: boolean;
  llm_available: boolean;
}

export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const { data } = await client.post(`/fmea/${fmeaId}/recommend`, request, { signal });
  return data;
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit src/api/recommendation.ts 2>&1 | head -20`
Expected: 无错误输出（或只有不相关的类型错误）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/recommendation.ts
git commit -m "feat(rec): add frontend recommendation API client"
```

---

## Task 10: SmartSuggestionDropdown 组件

**Files:**
- Create: `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`

- [ ] **Step 1: 创建智能建议下拉组件**

```tsx
// frontend/src/components/dfmea/SmartSuggestionDropdown.tsx
import { useState, useEffect, useRef, useCallback } from "react";
import { Input, Dropdown, Tag, Spin, Alert, Typography } from "antd";
import { BulbOutlined, StarOutlined, SettingOutlined } from "@ant-design/icons";
import { getRecommendations, type Suggestion, type RecommendResponse } from "../../api/recommendation";

const { Text } = Typography;

interface SmartSuggestionDropdownProps {
  triggerType: "failure_mode" | "failure_effect" | "failure_cause" | "measure" | "optimization";
  context: Record<string, unknown>;
  fmeaId: string;
  onSelect: (suggestion: Suggestion) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
}

export default function SmartSuggestionDropdown({
  triggerType,
  context,
  fmeaId,
  onSelect,
  disabled = false,
  value,
  onChange,
}: SmartSuggestionDropdownProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<string>("");
  const [llmAvailable, setLlmAvailable] = useState(true);
  const [fallback, setFallback] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const fetchSuggestions = useCallback(
    async (inputValue: string) => {
      if (!inputValue || inputValue.length < 2 || !fmeaId) {
        setSuggestions([]);
        setOpen(false);
        return;
      }

      // Cancel previous request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setLoading(true);
      try {
        const res: RecommendResponse = await getRecommendations(
          fmeaId,
          { trigger_type: triggerType, context: { ...context, [contextKey(triggerType)]: inputValue } },
          abortRef.current.signal
        );
        setSuggestions(res.suggestions.slice(0, 5));
        setSource(res.source);
        setLlmAvailable(res.llm_available);
        setFallback(res.source === "rule_fallback");
        setOpen(res.suggestions.length > 0);
        setSelectedIndex(-1);
      } catch {
        // Silently ignore aborted requests
      } finally {
        setLoading(false);
      }
    },
    [fmeaId, triggerType, context]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    onChange?.(val);

    clearTimeout(debounceRef.current);
    if (val.length >= 2) {
      debounceRef.current = setTimeout(() => fetchSuggestions(val), 500);
    } else {
      setSuggestions([]);
      setOpen(false);
    }
  };

  const handleSelect = (suggestion: Suggestion) => {
    onSelect(suggestion);
    onChange?.(suggestion.name);
    setOpen(false);
    setSuggestions([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[selectedIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  // Cleanup
  useEffect(() => {
    return () => {
      clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    };
  }, []);

  const confidenceLabel = (c: number) => {
    if (c >= 0.7) return <Tag color="green">高</Tag>;
    if (c >= 0.4) return <Tag color="orange">中</Tag>;
    return <Tag color="default">低</Tag>;
  };

  const sourceIcon = (s: string) =>
    s === "llm" ? <StarOutlined style={{ color: "#722ed1" }} /> : <SettingOutlined style={{ color: "#1890ff" }} />;

  const dropdownContent = (
    <div style={{ width: 320, background: "#fff", borderRadius: 4, boxShadow: "0 2px 8px rgba(0,0,0,0.15)" }}>
      {fallback && (
        <Alert
          type="warning"
          message="AI 建议暂不可用，已使用规则引擎"
          banner
          style={{ fontSize: 12 }}
        />
      )}
      {!llmAvailable && (
        <Text type="secondary" style={{ display: "block", padding: "4px 12px", fontSize: 12 }}>
          仅规则引擎模式
        </Text>
      )}
      {suggestions.map((s, i) => (
        <div
          key={i}
          onClick={() => handleSelect(s)}
          style={{
            padding: "8px 12px",
            cursor: "pointer",
            background: i === selectedIndex ? "#f0f0f0" : "transparent",
            borderBottom: i < suggestions.length - 1 ? "1px solid #f0f0f0" : "none",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {sourceIcon(s.source)}
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13 }}>{s.name}</div>
            {s.explanation && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {s.explanation}
              </Text>
            )}
          </div>
          {confidenceLabel(s.confidence)}
        </div>
      ))}
    </div>
  );

  return (
    <Dropdown
      open={open && !disabled}
      dropdownRender={() => dropdownContent}
      trigger={[]}
      placement="bottomLeft"
    >
      <div style={{ position: "relative" }}>
        <Input
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          disabled={disabled}
          suffix={loading ? <Spin size="small" /> : <BulbOutlined style={{ color: "#faad14" }} />}
          style={{ width: "100%" }}
        />
      </div>
    </Dropdown>
  );
}

function contextKey(triggerType: string): string {
  const map: Record<string, string> = {
    failure_mode: "function_description",
    failure_effect: "failure_mode",
    failure_cause: "failure_mode",
    measure: "failure_mode",
    optimization: "failure_mode",
  };
  return map[triggerType] || "function_description";
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit src/components/dfmea/SmartSuggestionDropdown.tsx 2>&1 | head -20`
Expected: 无错误（或只有不相关的类型错误）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dfmea/SmartSuggestionDropdown.tsx
git commit -m "feat(rec): add SmartSuggestionDropdown component with debounce and keyboard support"
```

---

## Task 11: FMEA 编辑器集成

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`

**关键前提：** `FMEARow` 只包含 node IDs（如 `failureModeNodeId`），不包含显示值。所有显示值通过 `nodeMap.get(row.xxxNodeId)?.name` 获取。现有权限使用 `canEdit('fmea')` 而非 `isViewer`。推荐列替换 `Input.TextArea` 为 `SmartSuggestionDropdown`，同时退役旧的 InlineRecommendations 系统（见 Step 1）。

- [ ] **Step 1: 添加 import 和 fmeaId 变量**

在 `FMEAEditorPage.tsx` 的 import 区域添加：

```typescript
import SmartSuggestionDropdown from "../../../components/dfmea/SmartSuggestionDropdown";
```

在组件内部（`const { id } = useParams<{ id: string }>();` 之后）添加 fmeaId 别名：

```typescript
const fmeaId = id || "";
```

现有代码使用 `const { id } = useParams()` 获取路由参数，后续代码中统一使用 `fmeaId` 引用。

同时退役旧的 InlineRecommendations 系统：

1. **移除 import：** 删除 `import InlineRecommendations from "../../../components/dfmea/InlineRecommendations";`
2. **移除渲染：** 搜索 `InlineRecommendations` 的 JSX 使用（通常在表格下方的 `<InlineRecommendations ... />`），删除或注释掉
3. **移除 activateRecommendation 调用：** 搜索所有 `onFocus={() => activateRecommendation(...)}` 调用（存在于 S/O/D 列的 Input 组件上），逐个删除这些 onFocus 回调。注意：不要删除整个 Input 组件，只删除 `onFocus` prop。
4. **移除 activateRecommendation 函数和相关 state：** 确认所有调用点已清除后，删除 `activateRecommendation` 函数定义和相关的 `recommendation` state 变量
5. **保留 `dfmeaRules.ts` import 不动：** 如果没有其他地方使用它，可以一并移除；如果有（如 GenerationWizard），保留并标记 `@deprecated`

**执行顺序很重要：** 先删调用点（Step 3），再删定义（Step 4），否则编译会报错。

- [ ] **Step 2: 在失败模式列集成 SmartSuggestionDropdown**

找到失败模式列（key: `failureMode`），将 `Input.TextArea` 替换为 `SmartSuggestionDropdown`：

```tsx
{
  title: "失效模式",
  key: "failureMode",
  width: 130,
  render: (_: unknown, row: FMEARow) => {
    const node = nodeMap.get(row.failureModeNodeId);
    return (
      <SmartSuggestionDropdown
        triggerType="failure_mode"
        context={{
          function_description: nodeMap.get(row.functionNodeId)?.name || "",
        }}
        fmeaId={fmeaId}
        value={node?.name || ""}
        onChange={(val) => updateNode(row.failureModeNodeId, "name", val)}
        onSelect={(s) => updateNode(row.failureModeNodeId, "name", s.name)}
        disabled={!canEdit('fmea')}
      />
    );
  },
},
```

- [ ] **Step 3: 在失败效应列集成**

找到失效影响列（key: `failureEffect`）：

```tsx
{
  title: "失效影响",
  key: "failureEffect",
  width: 140,
  render: (_: unknown, row: FMEARow) => {
    if (!row.failureEffectNodeId) return "-";
    const node = nodeMap.get(row.failureEffectNodeId);
    return (
      <SmartSuggestionDropdown
        triggerType="failure_effect"
        context={{
          failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
          function_description: nodeMap.get(row.functionNodeId)?.name || "",
        }}
        fmeaId={fmeaId}
        value={node?.name || ""}
        onChange={(val) => updateNode(row.failureEffectNodeId!, "name", val)}
        onSelect={(s) => updateNode(row.failureEffectNodeId!, "name", s.name)}
        disabled={!canEdit('fmea')}
      />
    );
  },
},
```

- [ ] **Step 4: 在失败原因列集成**

找到失效原因列（搜索 `失效原因` 或 `failureCause`）：

```tsx
{
  title: "失效原因",
  key: "failureCause",
  width: 140,
  render: (_: unknown, row: FMEARow) => {
    if (!row.failureCauseNodeId) return "-";
    const node = nodeMap.get(row.failureCauseNodeId);
    const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
    return (
      <SmartSuggestionDropdown
        triggerType="failure_cause"
        context={{
          failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
          function_description: nodeMap.get(row.functionNodeId)?.name || "",
          severity: effectNode?.severity || 0,
        }}
        fmeaId={fmeaId}
        value={node?.name || ""}
        onChange={(val) => updateNode(row.failureCauseNodeId!, "name", val)}
        onSelect={(s) => updateNode(row.failureCauseNodeId!, "name", s.name)}
        disabled={!canEdit('fmea')}
      />
    );
  },
},
```

- [ ] **Step 5: 在预防措施列集成**

找到预防措施列（搜索 `预防措施` 或 `preventionControl`）。注意：现有列使用 `Input.TextArea`，此处替换：

```tsx
{
  title: "预防措施",
  key: "preventionControl",
  width: 140,
  render: (_: unknown, row: FMEARow) => {
    const nodeId = row.preventionControlIds[0];
    if (!nodeId) return "-";
    const node = nodeMap.get(nodeId);
    // 计算当前 AP 用于推荐上下文
    const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
    const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
    const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
    const ap = calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, detNode?.detection || 0);
    return (
      <SmartSuggestionDropdown
        triggerType="measure"
        context={{
          failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
          ap: ap,
        }}
        fmeaId={fmeaId}
        value={node?.name || ""}
        onChange={(val) => updateNode(nodeId, "name", val)}
        onSelect={(s) => updateNode(nodeId, "name", s.name)}
        disabled={!canEdit('fmea')}
      />
    );
  },
},
```

- [ ] **Step 6: 在检测措施列集成**

```tsx
{
  title: "检测措施",
  key: "detectionControl",
  width: 140,
  render: (_: unknown, row: FMEARow) => {
    const nodeId = row.detectionControlIds[0];
    if (!nodeId) return "-";
    const node = nodeMap.get(nodeId);
    const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
    const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
    const ap = calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, node?.detection || 0);
    return (
      <SmartSuggestionDropdown
        triggerType="measure"
        context={{
          failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
          ap: ap,
        }}
        fmeaId={fmeaId}
        value={node?.name || ""}
        onChange={(val) => updateNode(nodeId, "name", val)}
        onSelect={(s) => updateNode(nodeId, "name", s.name)}
        disabled={!canEdit('fmea')}
      />
    );
  },
},
```

- [ ] **Step 7: 在建议措施列集成（保留 add 按钮路径）**

找到建议措施列（key: `recommendedAction`）。**关键：当 `recommendedActionIds.length === 0` 时，保留现有的 `+ 添加` 按钮**，只有存在 action node 时才显示 SmartSuggestionDropdown：

```tsx
{
  title: "建议措施",
  key: "recommendedAction",
  width: 140,
  render: (_: unknown, row: FMEARow) => {
    if (row.recommendedActionIds.length === 0) {
      // 保留现有的 "+ 添加" 按钮逻辑（创建 RecommendedAction 节点）
      return (
        <Button
          size="small"
          type="dashed"
          disabled={!canEdit('fmea')}
          onClick={() => {
            const ts = Date.now();
            const raId = `n${ts}_ra`;
            const newNode: GraphNode = {
              id: raId,
              type: "RecommendedAction",
              name: "新建议措施",
              severity: 0,
              occurrence: 0,
              detection: 0,
            };
            const sourceId = row.failureCauseNodeId || row.failureModeNodeId;
            const newEdge: GraphEdge = { source: sourceId, target: raId, type: "OPTIMIZED_BY" };
            setNodes((prev) => [...prev, newNode]);
            setEdges((prev) => [...prev, newEdge]);
          }}
        >
          + 添加
        </Button>
      );
    }
    // 已有 action node → 显示 SmartSuggestionDropdown
    const nodeId = row.recommendedActionIds[0];
    const node = nodeMap.get(nodeId);
    const effectNode = row.failureEffectNodeId ? nodeMap.get(row.failureEffectNodeId) : null;
    const causeNode = row.failureCauseNodeId ? nodeMap.get(row.failureCauseNodeId) : null;
    const detNode = row.detectionControlIds.length > 0 ? nodeMap.get(row.detectionControlIds[0]) : null;
    return (
      <SmartSuggestionDropdown
        triggerType="optimization"
        context={{
          failure_mode: nodeMap.get(row.failureModeNodeId)?.name || "",
          severity: effectNode?.severity || 0,
          occurrence: causeNode?.occurrence || 0,
          detection: detNode?.detection || 0,
          ap: calculateAP(effectNode?.severity || 0, causeNode?.occurrence || 0, detNode?.detection || 0),
        }}
        fmeaId={fmeaId}
        value={node?.name || ""}
        onChange={(val) => updateNode(nodeId, "name", val)}
        onSelect={(s) => updateNode(nodeId, "name", s.name)}
        disabled={!canEdit('fmea')}
      />
    );
  },
},
```

- [ ] **Step 8: 验证前端构建**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npm run build 2>&1 | tail -5`
Expected: 构建成功（`✓ built in ...`），可能有 warnings 但无 errors

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(rec): integrate SmartSuggestionDropdown into FMEA editor columns"
```

---

## Task 12: 后端端到端验证

- [ ] **Step 1: 运行数据库迁移**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic upgrade head`
Expected: `Running upgrade ... -> 20260601_rec_cache`

- [ ] **Step 2: 启动后端服务**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &`
Expected: `Application startup complete.`

- [ ] **Step 3: 测试推荐端点（规则引擎模式）**

Run:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -d "username=engineer&password=Engineer@2026" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 获取一个 FMEA ID
FMEA_ID=$(curl -s http://localhost:8000/api/fmea -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)['items'][0]['fmea_id'])")

# 调用推荐接口
curl -s -X POST "http://localhost:8000/api/fmea/$FMEA_ID/recommend" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"trigger_type":"failure_mode","context":{"function_description":"密封腔体"}}' | python -m json.tool
```

Expected:
```json
{
    "suggestions": [
        {"name": "密封失效", "confidence": 0.7, "source": "rule", "explanation": "动词「密封」匹配"},
        ...
    ],
    "source": "rule",
    "cached": false,
    "llm_available": false
}
```

- [ ] **Step 4: 测试缓存命中**

再次调用相同请求：
```bash
curl -s -X POST "http://localhost:8000/api/fmea/$FMEA_ID/recommend" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"trigger_type":"failure_mode","context":{"function_description":"密封腔体"}}' | python -m json.tool
```

Expected: `"cached": true`

- [ ] **Step 5: 测试权限（viewer 应返回 403）**

```bash
VIEWER_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -d "username=viewer&password=Viewer@2026" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST "http://localhost:8000/api/fmea/$FMEA_ID/recommend" \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"trigger_type":"failure_mode","context":{"function_description":"密封腔体"}}'
```

Expected: `{"detail":"编辑权限不足"}` (403)

- [ ] **Step 6: Commit 最终状态**

```bash
git add -A
git commit -m "feat: FMEA smart recommendation system - rule engine + LLM hybrid with caching"
```
