from pydantic import BaseModel


class ReviewSkillResponse(BaseModel):
    skill_id: str
    tenant_schema: str | None
    name: str
    content: str
    version: int
    is_active: bool


class ReviewSkillUpsert(BaseModel):
    content: str
