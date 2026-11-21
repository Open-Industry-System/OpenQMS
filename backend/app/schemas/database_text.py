"""Reject PostgreSQL-invalid NUL without imposing a manual-text length limit."""
from pydantic import BaseModel, field_validator


def reject_database_nul(value):
    if isinstance(value, str):
        if '\x00' in value:
            raise ValueError('Text contains an invalid character')
    elif isinstance(value, dict):
        for key, item in value.items():
            reject_database_nul(key)
            reject_database_nul(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_database_nul(item)
    return value


class DatabaseTextInput(BaseModel):
    @field_validator('*')
    @classmethod
    def database_text(cls, value):
        return reject_database_nul(value)
