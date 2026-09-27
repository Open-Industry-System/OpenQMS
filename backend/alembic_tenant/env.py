"""Independent tenant revision environment. No public migration history or URL fallback."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

from app.core.tenant_utils import strict_tenant_search_path_sql

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

connection = config.attributes.get("connection")
schema_name = config.attributes.get("schema_name")
if connection is None or schema_name is None:
    raise RuntimeError("Tenant Alembic requires the caller's locked connection and validated schema")
strict_tenant_search_path_sql(schema_name)
context.configure(connection=connection, version_table="tenant_schema_version",
                  version_table_schema=schema_name, transactional_ddl=True)
with context.begin_transaction():
    connection.execute(text(strict_tenant_search_path_sql(schema_name)))
    context.run_migrations()
