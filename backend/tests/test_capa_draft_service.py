# backend/tests/test_capa_draft_service.py
import asyncio
import time
import uuid
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.capa_draft_service as capa_draft_service
from app.config import settings
from app.schemas.capa_draft import DraftRequest, STEP_SCHEMA_MAP
from app.services.agent import provider_adapter
from app.services.capa_draft_service import (
    generate_draft,
    _render_structured,
    _build_prompt,
    _build_fmea_context,
    MAX_PROMPT_CHARS,
    _STEP_PRECONDITIONS,
    _FIELD_MIN_LENGTH,
    RATE_LIMIT_PER_MIN,
    _draft_cache,
    _rate_limit,
    _in_flight,
)


# ---------- 初始化 ----------

class _FakeReq:
    """Clean request double: avoids MagicMock auto-creating app.state.llm_provider.
    Timeout intentionally unset so generate_draft falls back to settings.CAPA_DRAFT_LLM_TIMEOUT."""
    class app:
        class state:
            pass


class _PC:
    model = "test-model"


@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    """每个测试前清理全局状态"""
    _draft_cache.clear()
    _rate_limit.clear()
    _in_flight.clear()
    # 固定超时，避免环境差异
    monkeypatch.setattr(settings, "CAPA_DRAFT_LLM_TIMEOUT", 15)
    # Default provider_adapter stubs so MagicMock db tests don't crash on build_client.
    async def _default_client(db_arg):
        return _PC()
    monkeypatch.setattr(provider_adapter, "build_client", _default_client)
    async def _default_complete(pc, prompt, schema):
        raise RuntimeError("unexpected complete_json call")
    monkeypatch.setattr(provider_adapter, "complete_json", _default_complete)


class TestGenerateDraftSuccess:
    """Issue 17: 成功路径完整断言"""

    @pytest.mark.asyncio
    async def test_draft_success(self, monkeypatch):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        async def _complete_json(pc, prompt, schema):
            return {
                "structured_data": {
                    "problem_statement": "陈述", "affected_product": "DC-DC-100",
                    "defect_description": "描述", "occurrence_context": "场景", "impact_scope": "范围",
                }
            }

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _complete_json)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        resp = await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())

        assert resp["step"] == "d2"
        assert "request_id" in resp
        assert resp["content"].startswith("问题陈述")
        assert resp["structured_data"]["problem_statement"] == "陈述"

    @pytest.mark.asyncio
    async def test_paragraph_format(self, monkeypatch):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        async def _complete_json(pc, prompt, schema):
            return {"content": "这是一段描述"}

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _complete_json)

        req = DraftRequest(format="paragraph", request_id=str(uuid.uuid4()))
        resp = await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())

        assert resp["content"] == "这是一段描述"
        assert resp["structured_data"] is None
        assert resp["step"] == "d2"

    @pytest.mark.asyncio
    async def test_cache_hit(self, monkeypatch):
        """Issue 18: 相同参数应命中缓存"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        call_count = 0
        async def _complete_json(pc, prompt, schema):
            nonlocal call_count
            call_count += 1
            return {
                "structured_data": {"problem_statement": "缓存测试", "affected_product": "A", "defect_description": "B", "occurrence_context": "C", "impact_scope": "D"}
            }

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _complete_json)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        resp1 = await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        resp2 = await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())

        assert resp1["content"] == resp2["content"]
        assert call_count == 1


class TestGenerateDraftValidation:
    """Issue 15: 前置条件校验"""

    @pytest.mark.asyncio
    async def test_invalid_request_id(self):
        """request_id 非标准 UUID → 400, 审计仍然写入"""
        req = DraftRequest(format="structured", request_id="not-a-uuid")
        audit_session = MagicMock()
        audit_session.commit = AsyncMock()
        audit_session.rollback = AsyncMock()
        audit_session.add = MagicMock()
        audit_cm = MagicMock()
        audit_cm.__aenter__ = AsyncMock(return_value=audit_session)
        audit_cm.__aexit__ = AsyncMock(return_value=False)
        user = MagicMock()
        user.user_id = uuid.uuid4()
        with patch("app.services.capa_draft_service.get_tenant_aware_session", return_value=audit_cm):
            with pytest.raises(HTTPException) as exc:
                await generate_draft(MagicMock(), uuid.uuid4(), "d2", req, user, _FakeReq())
        assert exc.value.status_code == 400
        assert "request_id" in exc.value.detail
        assert audit_session.commit.called  # audit written even on 400

    @pytest.mark.asyncio
    async def test_non_v4_request_id(self):
        """request_id 是 UUID 但非 v4 → 400, 审计仍然写入"""
        req = DraftRequest(format="structured", request_id="192a2fa8-6082-11f1-84b8-12fd368e6bd2")
        audit_session = MagicMock()
        audit_session.commit = AsyncMock()
        audit_session.rollback = AsyncMock()
        audit_session.add = MagicMock()
        audit_cm = MagicMock()
        audit_cm.__aenter__ = AsyncMock(return_value=audit_session)
        audit_cm.__aexit__ = AsyncMock(return_value=False)
        user = MagicMock()
        user.user_id = uuid.uuid4()
        with patch("app.services.capa_draft_service.get_tenant_aware_session", return_value=audit_cm):
            with pytest.raises(HTTPException) as exc:
                await generate_draft(MagicMock(), uuid.uuid4(), "d2", req, user, _FakeReq())
        assert exc.value.status_code == 400
        assert "request_id" in exc.value.detail
        assert audit_session.commit.called  # audit written even on 400

    @pytest.mark.asyncio
    async def test_unsupported_step(self):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d9", req, user, _FakeReq())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_archived_status(self):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "ARCHIVED"
        capa.title = "已归档报告"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_insufficient_data(self):
        """Issue 15: 字段不足 → 409（非 422）"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "短"  # 小于 _FIELD_MIN_LENGTH["title"]=6
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_status_mismatch_d3(self):
        """D3 步骤但状态不是 D3_INTERIM → 409"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"  # 只允许 d2
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = "已有描述"
        capa.d3_interim = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d3", req, user, _FakeReq())
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_backward_step_blocked(self):
        """D8_CLOSURE 状态下请求 d2 → 409（不允许回头草拟）"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D8_CLOSURE"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = "已有描述"

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_d1_team_status_blocked(self):
        """D1_TEAM 状态下请求 d2 → 409（D1 无可草拟步骤）"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D1_TEAM"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_closed_status_blocked(self):
        """CLOSED 状态下请求 d8 → 409（已关闭无可草拟步骤）"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "CLOSED"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = "描述"

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d8", req, user, _FakeReq())
        assert exc.value.status_code == 409


class TestRateLimitAndErrors:
    """Issue 16: 限流与异常路径"""

    @pytest.mark.asyncio
    async def test_rate_limit(self, monkeypatch):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))

        # 连续调用 11 次（超限制 10 次/分钟）
        for i in range(RATE_LIMIT_PER_MIN):
            _rate_limit.setdefault(str(user.user_id), []).append(time.time())

        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_llm_timeout(self, monkeypatch):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        async def _slow_complete(pc, prompt, schema):
            await asyncio.sleep(2)
            return {}

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _slow_complete)

        monkeypatch.setattr(settings, "CAPA_DRAFT_LLM_TIMEOUT", 0.1)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 504

    @pytest.mark.asyncio
    async def test_llm_invalid_json(self, monkeypatch):
        """Issue 14: LLM 返回非法 JSON → 422（非 503）"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        async def _bad_complete(pc, prompt, schema):
            raise Exception("JSON decode error")

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _bad_complete)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 422


class TestBuildPrompt:
    """Issue 6/21: Prompt 构建与截断策略"""

    def test_prompt_truncation(self):
        """超长字段应被截断，系统指令保留"""
        capa = MagicMock()
        capa.title = "A" * 5000
        capa.document_no = "8D-2026-001"
        capa.d2_description = "B" * 5000
        capa.d3_interim = ""
        capa.d4_root_cause = ""
        capa.d5_correction = ""
        capa.d6_verification = ""
        capa.d7_prevention = ""
        capa.d8_closure = ""
        capa.product_line_code = "DC-DC-100"
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        prompt = _build_prompt(capa, "d2", "structured", None)
        assert len(prompt) <= MAX_PROMPT_CHARS
        assert "【用户数据结束】" in prompt
        assert "...（已截断）" in prompt or len(prompt) < 5000

    def test_prompt_fixed_section_too_long(self):
        """Issue 6: 固定部分超限应抛配置错误"""
        import app.services.capa_draft_service as svc
        orig_max = svc.MAX_PROMPT_CHARS
        try:
            svc.MAX_PROMPT_CHARS = 100  # 极小值，让固定部分必然超限
            capa = MagicMock()
            capa.title = "测试"
            capa.document_no = "8D-2026-001"
            capa.d2_description = ""
            capa.d3_interim = ""
            capa.d4_root_cause = ""
            capa.d5_correction = ""
            capa.d6_verification = ""
            capa.d7_prevention = ""
            capa.d8_closure = ""
            capa.product_line_code = "DC-DC-100"
            capa.fmea_ref_id = None
            capa.fmea_node_id = None
            with pytest.raises(ValueError) as exc:
                _build_prompt(capa, "d2", "structured", None)
            assert "固定部分" in str(exc.value)
        finally:
            svc.MAX_PROMPT_CHARS = orig_max


class TestFMEAContext:
    """Issue 12/21: FMEA 上下文提取"""

    @pytest.mark.asyncio
    async def test_fmea_context_no_link(self):
        """无关联时应返回提示文本"""
        capa = MagicMock()
        capa.fmea_ref_id = None
        capa.fmea_node_id = None
        capa.product_line_code = "DC-DC-100"

        db = MagicMock()
        user = MagicMock()
        user.role_definition.bypass_row_level_security = True

        result = await _build_fmea_context(db, capa, user)
        assert result is None


class TestProductLineEnforcement:
    """Issue 20: 产品线隔离"""

    @pytest.mark.asyncio
    async def test_product_line_access_denied(self, monkeypatch):
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = False

        # 模拟 enforce 内部查询 db.execute 返回空（用户无该产品线权限）
        mock_result = MagicMock()
        mock_result.all.return_value = []  # 无权限
        db.execute = AsyncMock(return_value=mock_result)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_product_line_access_allowed(self, monkeypatch):
        """有权限时应正常通过产品线检查"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = False

        # 模拟 enforce 内部查询返回用户有权限的产品线
        mock_result = MagicMock()
        mock_result.all.return_value = [("DC-DC-100",)]
        db.execute = AsyncMock(return_value=mock_result)

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        async def _complete_json(pc, prompt, schema):
            return {
                "structured_data": {
                    "problem_statement": "问题描述",
                    "affected_product": "产品A",
                    "defect_description": "缺陷",
                    "occurrence_context": "场景",
                    "impact_scope": "范围",
                }
            }

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _complete_json)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        resp = await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
        assert resp["step"] == "d2"

    @pytest.mark.asyncio
    async def test_inflight_deduplication(self, monkeypatch):
        """Issue 19: 并发相同请求只调用一次 LLM"""
        from app.services import capa_draft_service

        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        call_count = 0
        async def _slow_complete(pc, prompt, schema):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return {
                "structured_data": {
                    "problem_statement": "测试", "affected_product": "DC-DC-100",
                    "defect_description": "描述", "occurrence_context": "场景", "impact_scope": "范围",
                }
            }

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _slow_complete)

        async def mock_enforce(*a, **k):
            pass
        monkeypatch.setattr(capa_draft_service, "enforce_product_line_access", mock_enforce)

        request_id = str(uuid.uuid4())
        req = DraftRequest(format="structured", request_id=request_id)

        task1 = asyncio.create_task(generate_draft(db, capa.report_id, "d2", req, user, _FakeReq()))
        task2 = asyncio.create_task(generate_draft(db, capa.report_id, "d2", req, user, _FakeReq()))

        result1, result2 = await asyncio.gather(task1, task2)
        assert result1["content"] == result2["content"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_audit_log(self, monkeypatch):
        """Issue 22: 成功/失败均写审计日志（独立 session）"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"
        capa.title = "测试报告标题"
        capa.document_no = "8D-2026-001"
        capa.product_line_code = "DC-DC-100"
        capa.d2_description = ""
        capa.fmea_ref_id = None
        capa.fmea_node_id = None

        db = MagicMock()
        db.get = AsyncMock(return_value=capa)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = MagicMock()
        user.user_id = uuid.uuid4()
        user.role_definition.bypass_row_level_security = True

        class _PC:
            model = "test-model"

        async def _build_client(db_arg):
            return _PC()

        async def _complete_json(pc, prompt, schema):
            return {
                "structured_data": {
                    "problem_statement": "审计测试", "affected_product": "A",
                    "defect_description": "B", "occurrence_context": "C", "impact_scope": "D",
                }
            }

        monkeypatch.setattr(provider_adapter, "build_client", _build_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _complete_json)

        # Mock get_tenant_aware_session for audit log isolation
        audit_session = MagicMock()
        audit_session.commit = AsyncMock()
        audit_session.rollback = AsyncMock()
        audit_session.add = MagicMock()
        audit_cm = MagicMock()
        audit_cm.__aenter__ = AsyncMock(return_value=audit_session)
        audit_cm.__aexit__ = AsyncMock(return_value=False)
        with patch("app.services.capa_draft_service.get_tenant_aware_session", return_value=audit_cm):
            req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
            await generate_draft(db, capa.report_id, "d2", req, user, _FakeReq())
            assert audit_session.commit.called


# ---------- P1-D provider migration tests ----------

@pytest.mark.asyncio
async def test_draft_uses_complete_json_and_no_write_audit_raw(
    db, default_factory, admin_user, monkeypatch
):
    """generate_draft calls provider_adapter.complete_json (not llm_provider.complete);
    does NOT introduce write_audit_raw (keeps existing AI_DRAFT AuditLog audit)."""
    async def _ok_client(db_arg):
        return _PC()
    async def _ok_complete(pc, prompt, schema):
        # paragraph format validates against ParagraphLLMOutput(content: str)
        return {"content": "AI 草稿正文"}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)

    # Spy: write_audit_raw must NOT be called
    from app.services.agent import audit as audit_mod
    raw_calls = []
    async def _spy_raw(*a, **k):
        raw_calls.append(True)
        raise AssertionError("write_audit_raw must not be introduced in CAPA draft")
    monkeypatch.setattr(audit_mod, "write_audit_raw", _spy_raw)

    from app.services.capa_draft_service import generate_draft
    from app.schemas.capa_draft import DraftRequest
    from app.models.capa import CAPAEightD
    # CAPAEightD: document_no (not doc_no) is the field; title is nullable=False.
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no="8D-2026-902", title="测试标题足够长",
                      factory_id=default_factory.id, product_line_code="DC-DC-100",
                      status="D2_DESCRIPTION")
    db.add(capa); await db.commit()

    # paragraph format -> no structured schema validation; request_id is parsed as
    # UUID internally, so pass a valid UUID4 string (not "r1").
    req = DraftRequest(format="paragraph", request_id=str(uuid.uuid4()))
    # build a fake Request with app.state carrying timeout
    class _Req:
        class app:
            class state:
                capa_draft_llm_timeout = 30
    result = await generate_draft(db, capa.report_id, "d2", req, admin_user, _Req())
    assert raw_calls == []  # no write_audit_raw introduced
    assert result is not None


@pytest.mark.asyncio
async def test_draft_503_when_pc_none_no_attribute_error(
    db, default_factory, admin_user, monkeypatch
):
    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    from app.services.capa_draft_service import generate_draft
    from app.schemas.capa_draft import DraftRequest
    from app.models.capa import CAPAEightD
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no="8D-2026-903", title="测试标题足够长",
                      factory_id=default_factory.id, product_line_code="DC-DC-100",
                      status="D2_DESCRIPTION")
    db.add(capa); await db.commit()
    req = DraftRequest(format="paragraph", request_id=str(uuid.uuid4()))
    class _Req:
        class app:
            class state:
                capa_draft_llm_timeout = 30
    with pytest.raises(HTTPException) as ei:
        await generate_draft(db, capa.report_id, "d2", req, admin_user, _Req())
    assert ei.value.status_code == 503
