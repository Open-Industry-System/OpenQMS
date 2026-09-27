"""Independent tenant revision environment. No public migration history or URL fallback."""
from logging.config import fileConfig

from alembic import context

from app.core.tenant_utils import strict_tenant_search_path_sql
from app.services.tenant_migrator import _bind_maintenance_sync

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

connection = config.attributes.get("connection")
schema_name = config.attributes.get("schema_name")
attempt = config.attributes.get("maintenance_attempt")
if connection is None or schema_name is None or attempt is None:
    raise RuntimeError("Tenant Alembic requires the caller's locked connection, attempt, and validated schema")
strict_tenant_search_path_sql(schema_name)
if schema_name != attempt.schema_name:
    raise RuntimeError("Tenant Alembic schema differs from the maintenance attempt")
context.configure(connection=connection, version_table="tenant_schema_version",
                  version_table_schema=schema_name, transactional_ddl=True)
with context.begin_transaction():
    _bind_maintenance_sync(connection, attempt)
    context.run_migrations()
