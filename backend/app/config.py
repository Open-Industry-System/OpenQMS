from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    ALGORITHM: str = "HS256"

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
