"""Tenant-local D4 delivery metadata, without body or implicit authorization."""
from datetime import datetime
from uuid import UUID as PyUUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import TenantBase


class AgentPluginDerivedSourceScope(TenantBase):
    __tablename__ = 'agent_plugin_derived_source_scopes'
    __table_args__ = (
        sa.PrimaryKeyConstraint('scope_id', name='pk_plugin_derived_scope'),
        sa.UniqueConstraint('plugin_grant_id', name='uq_plugin_derived_scope_grant'),
    )
    scope_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    plugin_grant_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_plugin_grants.grant_id', ondelete="RESTRICT", name='fk_plugin_derived_scope_plugin_grant_id'), nullable=False)
    target_report_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_plugin_derived_scope_target_report_id'), nullable=False)
    derived_projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    source_module: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    source_projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    fmea_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cause_node_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    actor_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_plugin_derived_scope_actor_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class AgentTaskDerivedSourceScope(TenantBase):
    __tablename__ = 'agent_task_derived_source_scopes'
    __table_args__ = (
        sa.PrimaryKeyConstraint('scope_id', name='pk_task_derived_scope'),
        sa.UniqueConstraint('task_grant_id', name='uq_task_derived_scope_grant'),
    )
    scope_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    task_grant_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_task_grants.grant_id', ondelete="RESTRICT", name='fk_task_derived_scope_task_grant_id'), nullable=False)
    target_report_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_task_derived_scope_target_report_id'), nullable=False)
    derived_projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    source_module: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    source_projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    fmea_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cause_node_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    actor_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_task_derived_scope_actor_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
