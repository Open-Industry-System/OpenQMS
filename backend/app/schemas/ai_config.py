from pydantic import BaseModel, Field, field_validator


class AIConfigOut(BaseModel):
    """Runtime AI configuration exposed to the admin UI."""

    llm_provider: str = ""
    llm_api_key: str = ""  # masked when read from the backend
    llm_model: str = ""
    llm_base_url: str = ""
    llm_timeout: int = Field(default=5, ge=1, le=120)
    capa_draft_llm_timeout: int = Field(default=15, ge=1, le=120)
    report_llm_timeout: int = Field(default=10, ge=1, le=120)

    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_base_url: str = ""
    embedding_dimensions: int = Field(default=1536, ge=1, le=4096)

    search_vector_weight: float = Field(default=0.7, ge=0, le=1)
    search_fulltext_weight: float = Field(default=0.3, ge=0, le=1)


class AIConfigUpdate(BaseModel):
    """Fields an admin can update from the UI."""

    llm_provider: str = ""
    llm_api_key: str = ""  # send empty to keep current; send new value to update
    llm_model: str = ""
    llm_base_url: str = ""
    llm_timeout: int = Field(default=5, ge=1, le=120)
    capa_draft_llm_timeout: int = Field(default=15, ge=1, le=120)
    report_llm_timeout: int = Field(default=10, ge=1, le=120)

    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_base_url: str = ""
    embedding_dimensions: int = Field(default=1536, ge=1, le=4096)

    search_vector_weight: float = Field(default=0.7, ge=0, le=1)
    search_fulltext_weight: float = Field(default=0.3, ge=0, le=1)

    @field_validator("search_vector_weight", "search_fulltext_weight")
    @classmethod
    def _precision(cls, v: float) -> float:
        return round(v, 2)


class ProviderTestResultSchema(BaseModel):
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None


class AIConfigTestResultSchema(BaseModel):
    llm: ProviderTestResultSchema
    embedding: ProviderTestResultSchema
