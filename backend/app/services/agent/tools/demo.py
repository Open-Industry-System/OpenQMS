from app.core.permissions import Module, PermissionLevel
from app.services import fmea_service
from app.services.agent.registry import AgentContext, agent_tool


@agent_tool(level="readonly", entity_type="factory",
            required_permission={"module": None, "min_level": None},
            description="Echo scope binding without exposing factory_id")
async def echo_factory(ctx: AgentContext) -> dict:
    return {"scope_bound": True, "factory_match": True}


@agent_tool(level="readonly", entity_type="fmea_document",
            required_permission={"module": Module.FMEA, "min_level": PermissionLevel.VIEW},
            description="列出当前工厂的 FMEA 文档")
async def list_fmea_documents(ctx: AgentContext, page: int = 1) -> dict:
    items, total = await fmea_service.list_fmeas(db=ctx.db, factory_id=ctx.factory_id, page=page)
    return {"items": [str(i.fmea_id) for i in items], "total": total}


@agent_tool(level="draft", entity_type="note",
            required_permission={"module": None, "min_level": None},
            description="生成一条草稿笔记（不落业务库）")
async def draft_note(ctx: AgentContext, text: str = "") -> dict:
    return {"draft": text or "（空草稿）"}


@agent_tool(level="commit", entity_type="tag", action="tag",
            required_permission={"module": None, "min_level": None},
            description="给实体打标签（commit demo）")
async def commit_tag(ctx: AgentContext, tag: str = "") -> dict:
    return {"tagged": tag}
