"""permission matrix — role_definitions, role_permissions, user_product_lines

Revision ID: 028_permission_matrix
Revises: 027
Create Date: 2026-06-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = '028_permission_matrix'
down_revision: Union[str, None] = '027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- permission matrix data ---------------------------------------------------
MODULES = [
    'fmea', 'capa', 'dashboard', 'audit', 'customer_quality', 'customer_audit',
    'supplier', 'iqc', 'ppap', 'spc', 'msa', 'planning', 'management_review',
    'user_mgmt', 'permission_mgmt', 'special_characteristic', 'quality_goal', 'scar',
]

# role_key -> {module: level}
PERMISSION_MATRIX = {
    'admin': {m: 5 for m in MODULES},
    'manager': {
        'fmea': 4, 'capa': 4, 'dashboard': 4, 'audit': 4,
        'customer_quality': 4, 'customer_audit': 4, 'supplier': 4,
        'iqc': 4, 'ppap': 4, 'spc': 4, 'msa': 4, 'planning': 4,
        'management_review': 4, 'user_mgmt': 1, 'permission_mgmt': 0,
        'special_characteristic': 4, 'quality_goal': 4, 'scar': 4,
    },
    'viewer': {
        'fmea': 1, 'capa': 1, 'dashboard': 1, 'audit': 1,
        'customer_quality': 1, 'customer_audit': 1, 'supplier': 1,
        'iqc': 1, 'ppap': 1, 'spc': 1, 'msa': 1, 'planning': 1,
        'management_review': 1, 'user_mgmt': 0, 'permission_mgmt': 0,
        'special_characteristic': 1, 'quality_goal': 1, 'scar': 1,
    },
    'customer_qe': {
        'fmea': 1, 'capa': 2, 'dashboard': 1, 'audit': 1,
        'customer_quality': 3, 'customer_audit': 3, 'supplier': 1,
        'iqc': 0, 'ppap': 0, 'spc': 1, 'msa': 0, 'planning': 0,
        'management_review': 0, 'user_mgmt': 0, 'permission_mgmt': 0,
        'special_characteristic': 0, 'quality_goal': 0, 'scar': 1,
    },
    'supplier_qe': {
        'fmea': 1, 'capa': 2, 'dashboard': 1, 'audit': 1,
        'customer_quality': 0, 'customer_audit': 0, 'supplier': 3,
        'iqc': 3, 'ppap': 3, 'spc': 1, 'msa': 0, 'planning': 1,
        'management_review': 0, 'user_mgmt': 0, 'permission_mgmt': 0,
        'special_characteristic': 0, 'quality_goal': 0, 'scar': 3,
    },
    'field_qe': {
        'fmea': 3, 'capa': 3, 'dashboard': 1, 'audit': 1,
        'customer_quality': 1, 'customer_audit': 1, 'supplier': 1,
        'iqc': 1, 'ppap': 0, 'spc': 3, 'msa': 3, 'planning': 1,
        'management_review': 1, 'user_mgmt': 0, 'permission_mgmt': 0,
        'special_characteristic': 0, 'quality_goal': 0, 'scar': 1,
    },
    'planning_qe': {
        'fmea': 3, 'capa': 1, 'dashboard': 1, 'audit': 1,
        'customer_quality': 1, 'customer_audit': 1, 'supplier': 1,
        'iqc': 1, 'ppap': 3, 'spc': 1, 'msa': 0, 'planning': 3,
        'management_review': 1, 'user_mgmt': 0, 'permission_mgmt': 0,
        'special_characteristic': 3, 'quality_goal': 0, 'scar': 1,
    },
}


def _escape(val: str) -> str:
    """Single-quote-escape for raw SQL literals."""
    return val.replace("'", "''")


def upgrade() -> None:
    # ---- 1. role_definitions -------------------------------------------------
    op.create_table(
        'role_definitions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('role_key', sa.String(30), unique=True, nullable=False),
        sa.Column('name_zh', sa.String(50), nullable=False),
        sa.Column('name_en', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('is_editable', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('bypass_row_level_security', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---- 2. seed 7 role_definitions -----------------------------------------
    roles = [
        # (role_key, name_zh, name_en, description, is_system, is_editable, bypass, sort)
        ('admin',        '系统管理员',           'System Admin',  None, True,  False, True,  1),
        ('manager',      '质量经理',             'Quality Manager', None, True, True,  False, 2),
        ('viewer',       '只读用户',             'Viewer',        None, True,  False, False, 3),
        ('customer_qe',  '客户质量工程师',       'Customer QE',   None, True,  True,  False, 4),
        ('supplier_qe',  '供应商质量工程师',     'Supplier QE',   None, True,  True,  False, 5),
        ('field_qe',     '现场质量工程师',       'Field QE',      None, True,  True,  False, 6),
        ('planning_qe',  '前期策划质量工程师',   'Planning QE',   None, True,  True,  False, 7),
    ]
    for role_key, name_zh, name_en, desc, is_sys, is_edit, bypass, sort in roles:
        desc_sql = 'NULL' if desc is None else f"'{_escape(desc)}'"
        op.execute(
            f"INSERT INTO role_definitions "
            f"(role_key, name_zh, name_en, description, is_system, is_editable, "
            f" bypass_row_level_security, is_active, sort_order) "
            f"VALUES ('{_escape(role_key)}', '{_escape(name_zh)}', '{_escape(name_en)}', "
            f"  {desc_sql}, {str(is_sys).lower()}, {str(is_edit).lower()}, "
            f"  {str(bypass).lower()}, true, {sort})"
        )

    # ---- 3. role_permissions -------------------------------------------------
    op.create_table(
        'role_permissions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('role_id', UUID(as_uuid=True),
                  sa.ForeignKey('role_definitions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('module', sa.String(30), nullable=False),
        sa.Column('permission_level', sa.SmallInteger(), nullable=False),
    )
    op.create_unique_constraint(
        'uq_role_permissions_role_module', 'role_permissions', ['role_id', 'module']
    )

    # ---- 4. user_product_lines -----------------------------------------------
    op.create_table(
        'user_product_lines',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_line_code', sa.String(20),
                  sa.ForeignKey('product_lines.code', ondelete='CASCADE'), nullable=False),
    )
    op.create_unique_constraint(
        'uq_user_product_lines_user_pl', 'user_product_lines',
        ['user_id', 'product_line_code']
    )

    # ---- 5. add users.role_id (nullable initially) --------------------------
    op.add_column('users', sa.Column('role_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_users_role_id', 'users', 'role_definitions', ['role_id'], ['id']
    )

    # ---- 6. backfill role_id from role --------------------------------------
    op.execute(
        "UPDATE users u SET role_id = r.id "
        "FROM role_definitions r WHERE u.role = r.role_key"
    )

    # ---- 7. map quality_engineer -> field_qe --------------------------------
    op.execute(
        "UPDATE users u SET role_id = r.id "
        "FROM role_definitions r "
        "WHERE u.role = 'quality_engineer' AND r.role_key = 'field_qe'"
    )

    # ---- 8. set NOT NULL ----------------------------------------------------
    op.alter_column('users', 'role_id', nullable=False)

    # ---- 9. rename users.role -> legacy_role --------------------------------
    op.alter_column('users', 'role', new_column_name='legacy_role')

    # ---- 10. seed role_permissions -------------------------------------------
    for role_key, perms in PERMISSION_MATRIX.items():
        for module, level in perms.items():
            op.execute(
                f"INSERT INTO role_permissions (role_id, module, permission_level) "
                f"SELECT id, '{_escape(module)}', {level} "
                f"FROM role_definitions WHERE role_key = '{_escape(role_key)}'"
            )


def downgrade() -> None:
    # reverse 9: rename legacy_role -> role
    op.alter_column('users', 'legacy_role', new_column_name='role')

    # reverse 8+5: drop role_id column (FK drops automatically)
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')
    op.drop_column('users', 'role_id')

    # reverse 4
    op.drop_table('user_product_lines')

    # reverse 3
    op.drop_table('role_permissions')

    # reverse 1
    op.drop_table('role_definitions')
