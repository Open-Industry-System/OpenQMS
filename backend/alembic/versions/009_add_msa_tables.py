"""Add 17 MSA tables: gauges, calibrations, and 5 study types (GRR, bias, linearity, stability, attribute)."""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009_add_msa_tables"
down_revision: Union[str, None] = "008_spc_v1_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Gauges
    op.create_table(
        "gauges",
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gauge_no", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("resolution", sa.Float, nullable=True),
        sa.Column("measuring_range", sa.String(100), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("calibration_cycle_days", sa.Integer, nullable=True),
        sa.Column("next_calibration_date", sa.Date, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "gauge_calibrations",
        sa.Column("calibration_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="CASCADE"), nullable=False),
        sa.Column("calibration_date", sa.Date, nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("certificate_no", sa.String(255), nullable=True),
        sa.Column("calibrated_by", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("next_calibration_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # GRR studies
    op.create_table(
        "grr_studies",
        sa.Column("study_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("method", sa.String(30), nullable=False, server_default="average_range"),
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("tolerance_upper", sa.Float, nullable=True),
        sa.Column("tolerance_lower", sa.Float, nullable=True),
        sa.Column("reference_value", sa.Float, nullable=True),
        sa.Column("appraiser_count", sa.Integer, nullable=False, server_default="3"),
        sa.Column("part_count", sa.Integer, nullable=False, server_default="10"),
        sa.Column("trial_count", sa.Integer, nullable=False, server_default="3"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "grr_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("appraiser_name", sa.String(100), nullable=False),
        sa.Column("part_no", sa.String(100), nullable=False),
        sa.Column("trial_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_grr_measurements_study", "grr_measurements", ["study_id"])

    op.create_table(
        "grr_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("ev", sa.Float, nullable=False),
        sa.Column("av", sa.Float, nullable=False),
        sa.Column("grr", sa.Float, nullable=False),
        sa.Column("pv", sa.Float, nullable=False),
        sa.Column("tv", sa.Float, nullable=False),
        sa.Column("ndc", sa.Float, nullable=False),
        sa.Column("grr_percent_tol", sa.Float, nullable=False),
        sa.Column("grr_percent_tv", sa.Float, nullable=False),
        sa.Column("ev_percent", sa.Float, nullable=False),
        sa.Column("av_percent", sa.Float, nullable=False),
        sa.Column("pv_percent", sa.Float, nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Bias studies
    op.create_table(
        "bias_studies",
        sa.Column("study_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("reference_value", sa.Float, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="10"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "bias_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bias_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bias_measurements_study", "bias_measurements", ["study_id"])

    op.create_table(
        "bias_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bias_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("mean", sa.Float, nullable=False),
        sa.Column("bias", sa.Float, nullable=False),
        sa.Column("bias_percent", sa.Float, nullable=True),
        sa.Column("std_dev", sa.Float, nullable=False),
        sa.Column("t_statistic", sa.Float, nullable=False),
        sa.Column("p_value", sa.Float, nullable=False),
        sa.Column("lower_ci", sa.Float, nullable=True),
        sa.Column("upper_ci", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Linearity studies
    op.create_table(
        "linearity_studies",
        sa.Column("study_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("tolerance_upper", sa.Float, nullable=True),
        sa.Column("tolerance_lower", sa.Float, nullable=True),
        sa.Column("sample_size_per_reference", sa.Integer, nullable=False, server_default="5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "linearity_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("linearity_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_value", sa.Float, nullable=False),
        sa.Column("measured_value", sa.Float, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_linearity_measurements_study", "linearity_measurements", ["study_id"])

    op.create_table(
        "linearity_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("linearity_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slope", sa.Float, nullable=False),
        sa.Column("intercept", sa.Float, nullable=False),
        sa.Column("r_squared", sa.Float, nullable=False),
        sa.Column("linearity", sa.Float, nullable=False),
        sa.Column("linearity_percent", sa.Float, nullable=True),
        sa.Column("bias_at_lower", sa.Float, nullable=True),
        sa.Column("bias_at_upper", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Stability studies
    op.create_table(
        "stability_studies",
        sa.Column("study_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("reference_value", sa.Float, nullable=True),
        sa.Column("subgroup_size", sa.Integer, nullable=False, server_default="5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "stability_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stability_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement_date", sa.Date, nullable=False),
        sa.Column("sample_mean", sa.Float, nullable=False),
        sa.Column("sample_range", sa.Float, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stability_measurements_study", "stability_measurements", ["study_id"])

    op.create_table(
        "stability_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stability_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("ucl_mean", sa.Float, nullable=False),
        sa.Column("lcl_mean", sa.Float, nullable=True),
        sa.Column("cl_mean", sa.Float, nullable=False),
        sa.Column("ucl_range", sa.Float, nullable=False),
        sa.Column("lcl_range", sa.Float, nullable=True),
        sa.Column("cl_range", sa.Float, nullable=False),
        sa.Column("cpk", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Attribute studies
    op.create_table(
        "attribute_studies",
        sa.Column("study_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="SET NULL"), nullable=True),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("method", sa.String(30), nullable=False, server_default="risk_analysis"),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="50"),
        sa.Column("known_standard_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "attribute_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("attribute_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("appraiser_name", sa.String(100), nullable=False),
        sa.Column("part_no", sa.String(100), nullable=False),
        sa.Column("known_standard", sa.String(10), nullable=False),
        sa.Column("appraiser_decision", sa.String(10), nullable=False),
        sa.Column("trial_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attribute_measurements_study", "attribute_measurements", ["study_id"])

    op.create_table(
        "attribute_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("attribute_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("effectiveness", sa.Float, nullable=False),
        sa.Column("miss_rate", sa.Float, nullable=False),
        sa.Column("false_alarm_rate", sa.Float, nullable=False),
        sa.Column("kappa_within", sa.Float, nullable=True),
        sa.Column("kappa_vs_standard", sa.Float, nullable=True),
        sa.Column("kappa_between", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "attribute_results", "attribute_measurements", "attribute_studies",
        "stability_results", "stability_measurements", "stability_studies",
        "linearity_results", "linearity_measurements", "linearity_studies",
        "bias_results", "bias_measurements", "bias_studies",
        "grr_results", "grr_measurements", "grr_studies",
        "gauge_calibrations", "gauges",
    ]:
        op.drop_table(table)
