from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "openqms2026"
    NEO4J_DATABASE: str = "neo4j"
    GRAPH_REPOSITORY: str = "jsonb"  # "jsonb" or "neo4j"

    # LLM 推荐（可选，未设置则纯规则引擎模式）
    LLM_PROVIDER: str = ""       # claude | openai | local | 留空=纯规则
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""          # 各 provider 有内部默认值
    LLM_BASE_URL: str = ""       # 仅 local 模式
    LLM_TIMEOUT: int = 5         # 超时秒数

    # Embedding & semantic search
    EMBEDDING_PROVIDER: str = ""        # "openai" | "ollama" | "" (follows LLM_PROVIDER)
    EMBEDDING_MODEL: str = ""           # optional override
    EMBEDDING_BASE_URL: str = "http://ollama:11434"
    EMBEDDING_DIMENSIONS: int = 1536    # 1536 for OpenAI, 768 for nomic-embed-text, 1024 for BGE-M3
    SEARCH_VECTOR_WEIGHT: float = 0.7   # weight for vector search in RRF
    SEARCH_FULLTEXT_WEIGHT: float = 0.3 # weight for fulltext search in RRF

    model_config = {"env_file": ".env"}

    @field_validator("SECRET_KEY")
    @classmethod
    def reject_default_secret(cls, v: str) -> str:
        if v == "dev-secret-key-change-in-production":
            raise ValueError(
                "SECRET_KEY must be changed from the default value. "
                "Set it via the SECRET_KEY environment variable or in your .env file."
            )
        return v


settings = Settings()
