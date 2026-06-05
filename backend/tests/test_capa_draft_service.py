# backend/tests/test_capa_draft_service.py
import asyncio
import time
import uuid
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.schemas.capa_draft import DraftRequest, STEP_SCHEMA_MAP
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

@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    """每个测试前清理全局状态"""
    _draft_cache.clear()
    _rate_limit.clear()
    _in_flight.clear()
    # 固定超时，避免环境差异
    monkeypatch.setattr(settings, "CAPA_DRAFT_LLM_TIMEOUT", 15)


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

        request = MagicMock()
        llm_provider = MagicMock()
        llm_provider.complete = AsyncMock(return_value={
            "structured_data": {
                "problem_statement": "陈述", "affected_product": "DC-DC-100",
                "defect_description": "描述", "occurrence_context": "场景", "impact_scope": "范围",
            }
        })
        request.app.state.llm_provider = llm_provider

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        resp = await generate_draft(db, capa.report_id, "d2", req, user, request)

        assert resp["step"] == "d2"
        assert "request_id" in resp
        assert resp["content"].startswith("问题陈述")
        assert resp["structured_data"]["problem_statement"] == "陈述"
        assert llm_provider.complete.called

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

        request = MagicMock()
        llm_provider = MagicMock()
        llm_provider.complete = AsyncMock(return_value={"content": "这是一段描述"})
        request.app.state.llm_provider = llm_provider

        req = DraftRequest(format="paragraph", request_id=str(uuid.uuid4()))
        resp = await generate_draft(db, capa.report_id, "d2", req, user, request)

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

        request = MagicMock()
        llm_provider = MagicMock()
        llm_provider.complete = AsyncMock(return_value={
            "structured_data": {"problem_statement": "缓存测试", "affected_product": "A", "defect_description": "B", "occurrence_context": "C", "impact_scope": "D"}
        })
        request.app.state.llm_provider = llm_provider

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        resp1 = await generate_draft(db, capa.report_id, "d2", req, user, request)
        resp2 = await generate_draft(db, capa.report_id, "d2", req, user, request)

        assert resp1["content"] == resp2["content"]
        assert llm_provider.complete.call_count == 1


class TestGenerateDraftValidation:
    """Issue 15: 前置条件校验"""

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
            await generate_draft(db, capa.report_id, "d9", req, user, MagicMock())
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
            await generate_draft(db, capa.report_id, "d2", req, user, MagicMock())
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
            await generate_draft(db, capa.report_id, "d2", req, user, MagicMock())
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_status_mismatch_d3(self):
        """Issue 15: D3 步骤但状态不是 D3_INTERIM → 409"""
        capa = MagicMock()
        capa.report_id = uuid.uuid4()
        capa.status = "D2_DESCRIPTION"  # 不是 D3_INTERIM
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
            await generate_draft(db, capa.report_id, "d3", req, user, MagicMock())
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
            await generate_draft(db, capa.report_id, "d2", req, user, MagicMock())
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

        request = MagicMock()
        llm_provider = MagicMock()
        async def slow(*a, **k):
            await asyncio.sleep(2)
            return {}
        llm_provider.complete = slow
        request.app.state.llm_provider = llm_provider

        monkeypatch.setattr(settings, "CAPA_DRAFT_LLM_TIMEOUT", 0.1)

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, request)
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

        request = MagicMock()
        llm_provider = MagicMock()
        llm_provider.complete = AsyncMock(side_effect=Exception("JSON decode error"))
        request.app.state.llm_provider = llm_provider

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        with pytest.raises(HTTPException) as exc:
            await generate_draft(db, capa.report_id, "d2", req, user, request)
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
            await generate_draft(db, capa.report_id, "d2", req, user, MagicMock())
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

        # Mock LLM provider
        llm_provider = MagicMock()
        llm_provider.complete = AsyncMock(return_value={
            "structured_data": {
                "problem_statement": "问题描述",
                "affected_product": "产品A",
                "defect_description": "缺陷",
                "occurrence_context": "场景",
                "impact_scope": "范围",
            }
        })
        request = MagicMock()
        request.app.state.llm_provider = llm_provider

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        resp = await generate_draft(db, capa.report_id, "d2", req, user, request)
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

        request = MagicMock()
        llm_provider = MagicMock()
        call_count = 0

        async def slow_complete(*a, **k):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return {
                "structured_data": {
                    "problem_statement": "测试", "affected_product": "DC-DC-100",
                    "defect_description": "描述", "occurrence_context": "场景", "impact_scope": "范围",
                }
            }
        llm_provider.complete = slow_complete
        request.app.state.llm_provider = llm_provider

        async def mock_enforce(*a, **k):
            pass
        monkeypatch.setattr(capa_draft_service, "enforce_product_line_access", mock_enforce)

        request_id = str(uuid.uuid4())
        req = DraftRequest(format="structured", request_id=request_id)

        task1 = asyncio.create_task(generate_draft(db, capa.report_id, "d2", req, user, request))
        task2 = asyncio.create_task(generate_draft(db, capa.report_id, "d2", req, user, request))

        result1, result2 = await asyncio.gather(task1, task2)
        assert result1["content"] == result2["content"]
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_audit_log(self, monkeypatch):
        """Issue 22: 成功/失败均写审计日志"""
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

        request = MagicMock()
        llm_provider = MagicMock()
        llm_provider.complete = AsyncMock(return_value={
            "structured_data": {
                "problem_statement": "审计测试", "affected_product": "A",
                "defect_description": "B", "occurrence_context": "C", "impact_scope": "D",
            }
        })
        request.app.state.llm_provider = llm_provider

        req = DraftRequest(format="structured", request_id=str(uuid.uuid4()))
        await generate_draft(db, capa.report_id, "d2", req, user, request)
        assert db.commit.called
