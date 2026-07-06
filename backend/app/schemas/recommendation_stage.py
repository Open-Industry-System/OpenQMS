from typing import Literal

from pydantic import BaseModel


class StageRunSchema(BaseModel):
    index: int
    name: str
    source: str
    status: Literal["pending", "running", "done", "skipped", "error"]
    hit_count: int
    summary: str
    error: str | None = None
    llm_attempted: int | None = None
    llm_succeeded: int | None = None
    llm_failed: int | None = None
