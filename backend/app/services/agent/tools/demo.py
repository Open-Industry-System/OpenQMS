from app.services.agent.registry import AgentContext, agent_tool


@agent_tool(level="readonly", entity_type="factory",
            required_permission={"module": None, "min_level": None},
            description="Echo scope binding without exposing factory_id")
async def echo_factory(ctx: AgentContext) -> dict:
    return {"scope_bound": True, "factory_match": True}


@agent_tool(level="commit", entity_type="tag", action="tag",
            required_permission={"module": None, "min_level": None},
            description="Tag something (commit demo)")
async def commit_tag(ctx: AgentContext, tag: str = "") -> dict:
    return {"tagged": tag}
