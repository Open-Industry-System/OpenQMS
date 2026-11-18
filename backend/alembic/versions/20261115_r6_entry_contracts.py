"""R6 additive source/correction contracts; preserve all R5 signed facts."""
from alembic import op
import sqlalchemy as sa

revision = '20261115_r6_entry_contracts'
down_revision = '20261115_r5_responses'
branch_labels = None
depends_on = None

TABLES = ('capa_r6_material_versions', 'capa_r6_entry_switches', 'capa_r6_report_snapshots', 'capa_r6_source_origins', 'agent_d4_candidate_commands', 'agent_d4_candidate_checkpoint_positions', 'capa_d4_candidates', 'capa_d4_candidate_sources', 'capa_r6_root_revision_bodies', 'capa_r6_root_revision_sources', 'capa_d5_measure_revisions', 'capa_r6_staff_receipts', 'capa_r6_root_delivery_bindings')
EXISTING_UNIQUES = (('agent_tasks', 'uq_r6_task_report', ('task_id', 'target_capa_id')), ('agent_runs', 'uq_r6_run_task', ('run_id', 'task_id')), ('agent_task_messages', 'uq_r6_message_task', ('message_id', 'task_id')), ('capa_d4_root_cause_revisions', 'uq_r6_root_report', ('revision_id', 'report_id')), ('agent_d5_basis_receipts', 'uq_r6_basis_root', ('receipt_id', 'report_id', 'revision_id')), ('agent_d4_recovery_checkpoints', 'uq_r6_checkpoint_task', ('checkpoint_id', 'task_id')))

def upgrade():
    for table, name, columns in EXISTING_UNIQUES:
        op.create_unique_constraint(name, table, list(columns))
    op.execute("""
CREATE TABLE capa_r6_material_versions (
	report_id UUID NOT NULL,
	counter BIGINT DEFAULT '0' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (report_id),
	CONSTRAINT ck_r6_material_counter CHECK (counter >= 0),
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_r6_entry_switches (
	switch_id UUID NOT NULL,
	epoch BIGINT NOT NULL,
	state VARCHAR(16) NOT NULL,
	actor_id UUID NOT NULL,
	evidence JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (switch_id),
	CONSTRAINT uq_r6_switch_epoch UNIQUE (epoch),
	CONSTRAINT ck_r6_switch_epoch CHECK (epoch >= 0),
	CONSTRAINT ck_r6_switch_state CHECK (state IN ('legacy','draining','switched')),
	CONSTRAINT ck_r6_switch_evidence CHECK (jsonb_typeof(evidence) = 'object'),
	FOREIGN KEY(actor_id) REFERENCES users (user_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_r6_report_snapshots (
	snapshot_id UUID NOT NULL,
	report_id UUID NOT NULL,
	kind VARCHAR(8) NOT NULL,
	version BIGINT NOT NULL,
	body TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (snapshot_id),
	CONSTRAINT uq_r6_snapshot_report UNIQUE (snapshot_id, report_id),
	CONSTRAINT uq_r6_snapshot_version UNIQUE (report_id, kind, version),
	CONSTRAINT ck_r6_snapshot_kind CHECK (kind IN ('d2','d3')),
	CONSTRAINT ck_r6_snapshot_version CHECK (version >= 0),
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_r6_source_origins (
	source_id UUID NOT NULL,
	report_id UUID NOT NULL,
	kind VARCHAR(24) NOT NULL,
	module VARCHAR(16) NOT NULL,
	object_id UUID NOT NULL,
	projection_id VARCHAR(160) NOT NULL,
	version VARCHAR(128) NOT NULL,
	factory_id UUID NOT NULL,
	product_line_code VARCHAR(20) NOT NULL,
	snapshot_id UUID,
	fmea_id UUID,
	node_id VARCHAR(128),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (source_id),
	FOREIGN KEY(snapshot_id, report_id) REFERENCES capa_r6_report_snapshots (snapshot_id, report_id) ON DELETE RESTRICT,
	CONSTRAINT uq_r6_origin_report UNIQUE (source_id, report_id),
	CONSTRAINT ck_r6_origin_coordinate CHECK ((kind = 'report_snapshot' AND module = 'capa' AND object_id = report_id AND snapshot_id IS NOT NULL AND fmea_id IS NULL AND node_id IS NULL AND projection_id IN ('capa.d2.snapshot.v1','capa.d3.snapshot.v1')) OR (kind = 'fmea_projection' AND module = 'fmea' AND object_id = fmea_id AND snapshot_id IS NULL AND fmea_id IS NOT NULL AND node_id IS NOT NULL AND projection_id = 'fmea.failure_cause.reference.v1')),
	CONSTRAINT ck_r6_origin_version CHECK (length(version) > 0),
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT,
	FOREIGN KEY(factory_id) REFERENCES factories (id) ON DELETE RESTRICT,
	FOREIGN KEY(fmea_id) REFERENCES fmea_documents (fmea_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE agent_d4_candidate_commands (
	command_id UUID NOT NULL,
	report_id UUID NOT NULL,
	task_id UUID NOT NULL,
	run_id UUID NOT NULL,
	command_key VARCHAR(128) NOT NULL,
	operation VARCHAR(16) NOT NULL,
	sequence BIGINT NOT NULL,
	request_hmac VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (command_id),
	FOREIGN KEY(task_id, report_id) REFERENCES agent_tasks (task_id, target_capa_id) ON DELETE RESTRICT,
	FOREIGN KEY(run_id, task_id) REFERENCES agent_runs (run_id, task_id) ON DELETE RESTRICT,
	CONSTRAINT uq_d4_candidate_command_key UNIQUE (task_id, command_key),
	CONSTRAINT uq_d4_candidate_command_sequence UNIQUE (task_id, sequence),
	CONSTRAINT uq_d4_candidate_command_target UNIQUE (command_id, report_id, task_id, run_id),
	CONSTRAINT ck_d4_candidate_sequence CHECK (sequence > 0),
	CONSTRAINT ck_d4_candidate_command_key CHECK (command_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
	CONSTRAINT ck_d4_candidate_command_hmac CHECK (request_hmac ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_d4_candidate_operation CHECK (operation IN ('save','alternative','replace')),
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE agent_d4_candidate_checkpoint_positions (
	checkpoint_id UUID NOT NULL,
	task_id UUID NOT NULL,
	watermark BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (checkpoint_id),
	FOREIGN KEY(checkpoint_id, task_id) REFERENCES agent_d4_recovery_checkpoints (checkpoint_id, task_id) ON DELETE RESTRICT,
	CONSTRAINT ck_d4_candidate_checkpoint_watermark CHECK (watermark >= 0),
	FOREIGN KEY(task_id) REFERENCES agent_tasks (task_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_d4_candidates (
	candidate_id UUID NOT NULL,
	report_id UUID NOT NULL,
	task_id UUID NOT NULL,
	run_id UUID NOT NULL,
	command_id UUID NOT NULL,
	original_text TEXT NOT NULL,
	supporting JSONB NOT NULL,
	opposing JSONB NOT NULL,
	missing_information JSONB NOT NULL,
	input_versions JSONB NOT NULL,
	state VARCHAR(16) NOT NULL,
	version BIGINT DEFAULT '1' NOT NULL,
	source_count INTEGER DEFAULT '1' NOT NULL,
	predecessor_id UUID,
	correction_message_id UUID,
	created_by UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (candidate_id),
	FOREIGN KEY(command_id, report_id, task_id, run_id) REFERENCES agent_d4_candidate_commands (command_id, report_id, task_id, run_id) ON DELETE RESTRICT,
	FOREIGN KEY(predecessor_id, report_id, task_id) REFERENCES capa_d4_candidates (candidate_id, report_id, task_id) ON DELETE RESTRICT,
	FOREIGN KEY(correction_message_id, task_id) REFERENCES agent_task_messages (message_id, task_id) ON DELETE RESTRICT,
	CONSTRAINT uq_d4_candidate_report UNIQUE (candidate_id, report_id),
	CONSTRAINT uq_d4_candidate_task UNIQUE (candidate_id, report_id, task_id),
	CONSTRAINT uq_d4_candidate_command UNIQUE (command_id),
	CONSTRAINT uq_d4_candidate_successor UNIQUE (predecessor_id),
	CONSTRAINT ck_d4_candidate_state CHECK (state IN ('pending','adopted','withdrawn','superseded')),
	CONSTRAINT ck_d4_candidate_version CHECK (version > 0),
	CONSTRAINT ck_d4_candidate_source_count CHECK (source_count > 0),
	CONSTRAINT ck_d4_candidate_correction CHECK ((predecessor_id IS NULL) = (correction_message_id IS NULL) AND predecessor_id IS DISTINCT FROM candidate_id),
	CONSTRAINT ck_d4_candidate_evidence CHECK (jsonb_typeof(supporting) = 'array' AND jsonb_typeof(opposing) = 'array' AND jsonb_typeof(missing_information) = 'array' AND jsonb_typeof(input_versions) = 'object'),
	CONSTRAINT ck_d4_candidate_text CHECK (octet_length(original_text) <= 16384 AND length(btrim(original_text)) > 0),
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT,
	FOREIGN KEY(created_by) REFERENCES users (user_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_d4_candidate_sources (
	candidate_id UUID NOT NULL,
	report_id UUID NOT NULL,
	source_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (candidate_id, source_id),
	FOREIGN KEY(candidate_id, report_id) REFERENCES capa_d4_candidates (candidate_id, report_id) ON DELETE RESTRICT,
	FOREIGN KEY(source_id, report_id) REFERENCES capa_r6_source_origins (source_id, report_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_r6_root_revision_bodies (
	revision_id UUID NOT NULL,
	report_id UUID NOT NULL,
	binding_state VARCHAR(24) NOT NULL,
	body TEXT NOT NULL,
	predecessor_id UUID,
	source_count INTEGER NOT NULL,
	origin_digest VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (revision_id),
	FOREIGN KEY(revision_id, report_id) REFERENCES capa_d4_root_cause_revisions (revision_id, report_id) ON DELETE RESTRICT,
	FOREIGN KEY(predecessor_id, report_id) REFERENCES capa_r6_root_revision_bodies (revision_id, report_id) ON DELETE RESTRICT,
	CONSTRAINT uq_r6_root_body_report UNIQUE (revision_id, report_id),
	CONSTRAINT ck_r6_root_binding CHECK ((binding_state = 'controlled' AND source_count > 0) OR (binding_state = 'legacy_unattested' AND source_count = 0)),
	CONSTRAINT ck_r6_root_digest CHECK (origin_digest ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_r6_root_predecessor CHECK (predecessor_id IS DISTINCT FROM revision_id)
)
""")
    op.execute("""
CREATE TABLE capa_r6_root_revision_sources (
	revision_id UUID NOT NULL,
	report_id UUID NOT NULL,
	source_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (revision_id, source_id),
	FOREIGN KEY(revision_id, report_id) REFERENCES capa_r6_root_revision_bodies (revision_id, report_id) ON DELETE RESTRICT,
	FOREIGN KEY(source_id, report_id) REFERENCES capa_r6_source_origins (source_id, report_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_d5_measure_revisions (
	revision_id UUID NOT NULL,
	report_id UUID NOT NULL,
	measure_id UUID NOT NULL,
	revision_no BIGINT NOT NULL,
	predecessor_id UUID,
	final_text TEXT NOT NULL,
	reason TEXT NOT NULL,
	actor_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (revision_id),
	FOREIGN KEY(predecessor_id, measure_id) REFERENCES capa_d5_measure_revisions (revision_id, measure_id) ON DELETE RESTRICT,
	CONSTRAINT uq_d5_measure_revision_measure UNIQUE (revision_id, measure_id),
	CONSTRAINT uq_d5_measure_revision_report UNIQUE (revision_id, report_id),
	CONSTRAINT uq_d5_measure_revision_no UNIQUE (measure_id, revision_no),
	CONSTRAINT uq_d5_measure_revision_successor UNIQUE (predecessor_id),
	CONSTRAINT ck_d5_measure_revision_predecessor CHECK (revision_no > 0 AND ((revision_no = 1 AND predecessor_id IS NULL) OR (revision_no > 1 AND predecessor_id IS NOT NULL))),
	CONSTRAINT ck_d5_measure_revision_text CHECK (octet_length(final_text) <= 16384 AND length(btrim(final_text)) > 0),
	CONSTRAINT ck_d5_measure_revision_reason CHECK (octet_length(reason) <= 16384 AND length(btrim(reason)) > 0),
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT,
	FOREIGN KEY(measure_id) REFERENCES capa_d5_measures (measure_id) ON DELETE RESTRICT,
	FOREIGN KEY(actor_id) REFERENCES users (user_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_r6_staff_receipts (
	receipt_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	operation_key VARCHAR(128) NOT NULL,
	operation VARCHAR(24) NOT NULL,
	request_hmac VARCHAR(64) NOT NULL,
	report_id UUID NOT NULL,
	candidate_id UUID,
	root_revision_id UUID,
	measure_revision_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (receipt_id),
	FOREIGN KEY(candidate_id, report_id) REFERENCES capa_d4_candidates (candidate_id, report_id) ON DELETE RESTRICT,
	FOREIGN KEY(root_revision_id, report_id) REFERENCES capa_r6_root_revision_bodies (revision_id, report_id) ON DELETE RESTRICT,
	FOREIGN KEY(measure_revision_id, report_id) REFERENCES capa_d5_measure_revisions (revision_id, report_id) ON DELETE RESTRICT,
	CONSTRAINT uq_r6_staff_operation_key UNIQUE (actor_id, operation_key),
	CONSTRAINT ck_r6_staff_operation_key CHECK (operation_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
	CONSTRAINT ck_r6_staff_hmac CHECK (request_hmac ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_r6_staff_result CHECK ((operation = 'd4_confirm' AND candidate_id IS NOT NULL AND root_revision_id IS NOT NULL AND measure_revision_id IS NULL) OR (operation = 'd4_withdraw' AND candidate_id IS NOT NULL AND root_revision_id IS NULL AND measure_revision_id IS NULL) OR (operation = 'd5_correct' AND measure_revision_id IS NOT NULL AND candidate_id IS NULL AND root_revision_id IS NULL)),
	FOREIGN KEY(actor_id) REFERENCES users (user_id) ON DELETE RESTRICT,
	FOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE capa_r6_root_delivery_bindings (
	receipt_id UUID NOT NULL,
	report_id UUID NOT NULL,
	revision_id UUID NOT NULL,
	origin_digest VARCHAR(64) NOT NULL,
	input_bindings JSONB NOT NULL,
	binding_hmac VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (receipt_id),
	FOREIGN KEY(receipt_id, report_id, revision_id) REFERENCES agent_d5_basis_receipts (receipt_id, report_id, revision_id) ON DELETE RESTRICT,
	FOREIGN KEY(revision_id, report_id) REFERENCES capa_r6_root_revision_bodies (revision_id, report_id) ON DELETE RESTRICT,
	CONSTRAINT ck_r6_delivery_digests CHECK (origin_digest ~ '^[0-9a-f]{64}$' AND binding_hmac ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_r6_delivery_inputs CHECK (jsonb_typeof(input_bindings) = 'array')
)
""")
    op.execute("""
CREATE FUNCTION r6_immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'R6 history is immutable' USING ERRCODE='23514'; END $$
""")
    for table in TABLES:
        if table not in {'capa_r6_material_versions', 'capa_d4_candidates'}:
            op.execute(f'CREATE TRIGGER r6_immutable_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION r6_immutable_history()')
    op.execute("""
CREATE FUNCTION r6_material_monotonic() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'R6 material version cannot be removed' USING ERRCODE='23514';
  END IF;
  IF NEW.report_id IS DISTINCT FROM OLD.report_id OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.counter <= OLD.counter THEN
    RAISE EXCEPTION 'R6 material version must advance' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
""")
    op.execute('CREATE TRIGGER r6_material_monotonic BEFORE UPDATE OR DELETE ON capa_r6_material_versions FOR EACH ROW EXECUTE FUNCTION r6_material_monotonic()')
    op.execute("""
CREATE FUNCTION r6_candidate_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'R6 candidate history is immutable' USING ERRCODE='23514';
  END IF;
  IF (to_jsonb(NEW) - 'state' - 'version') IS DISTINCT FROM (to_jsonb(OLD) - 'state' - 'version')
     OR OLD.state <> 'pending' OR NEW.state NOT IN ('adopted','withdrawn','superseded') OR NEW.version <> OLD.version + 1 THEN
    RAISE EXCEPTION 'R6 candidate history is immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
""")
    op.execute('CREATE TRIGGER r6_candidate_transition BEFORE UPDATE OR DELETE ON capa_d4_candidates FOR EACH ROW EXECUTE FUNCTION r6_candidate_transition()')
    op.execute("""
CREATE FUNCTION r6_validate_origin() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record; s record; f record;
BEGIN
  SELECT factory_id,product_line_code INTO STRICT r FROM capa_eightd WHERE report_id=NEW.report_id;
  IF NEW.kind = 'report_snapshot' THEN
    SELECT kind,version INTO STRICT s FROM capa_r6_report_snapshots WHERE snapshot_id=NEW.snapshot_id AND report_id=NEW.report_id;
    IF NEW.factory_id <> r.factory_id OR NEW.product_line_code <> r.product_line_code
       OR NEW.projection_id <> 'capa.' || s.kind || '.snapshot.v1' OR NEW.version <> s.version::text THEN
      RAISE EXCEPTION 'R6 snapshot origin coordinate mismatch' USING ERRCODE='23514';
    END IF;
  ELSE
    SELECT factory_id,product_line_code,graph_data INTO f FROM fmea_documents WHERE fmea_id=NEW.fmea_id;
    IF NOT FOUND OR NEW.factory_id <> f.factory_id OR NEW.product_line_code <> f.product_line_code
       OR NEW.version !~ '^[0-9a-f]{64}$' OR NOT EXISTS (
         SELECT 1 FROM jsonb_array_elements(coalesce(f.graph_data->'nodes','[]'::jsonb)) n
         WHERE n->>'id'=NEW.node_id AND n->>'type'='FailureCause') THEN
      RAISE EXCEPTION 'R6 FMEA origin coordinate mismatch' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$
""")
    op.execute('CREATE TRIGGER r6_validate_origin BEFORE INSERT ON capa_r6_source_origins FOR EACH ROW EXECUTE FUNCTION r6_validate_origin()')
    op.execute("""
CREATE FUNCTION r6_validate_correction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE report uuid; previous_no bigint;
BEGIN
  SELECT p.report_id INTO report FROM capa_d5_measures m JOIN capa_d5_proposals p ON p.proposal_id=m.proposal_id WHERE m.measure_id=NEW.measure_id;
  IF report IS DISTINCT FROM NEW.report_id THEN
    RAISE EXCEPTION 'R6 correction report mismatch' USING ERRCODE='23514';
  END IF;
  IF NEW.predecessor_id IS NOT NULL THEN
    SELECT revision_no INTO previous_no FROM capa_d5_measure_revisions WHERE revision_id=NEW.predecessor_id AND measure_id=NEW.measure_id;
    IF previous_no IS NULL OR previous_no + 1 <> NEW.revision_no THEN
      RAISE EXCEPTION 'R6 correction predecessor mismatch' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$
""")
    op.execute('CREATE TRIGGER r6_validate_correction BEFORE INSERT ON capa_d5_measure_revisions FOR EACH ROW EXECUTE FUNCTION r6_validate_correction()')
    op.execute("""
CREATE FUNCTION r6_preserve_adoption() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.measure_id,NEW.proposal_id,NEW.final_text,NEW.adopted_by,NEW.adopted_at,NEW.created_at)
     IS DISTINCT FROM ROW(OLD.measure_id,OLD.proposal_id,OLD.final_text,OLD.adopted_by,OLD.adopted_at,OLD.created_at) THEN
    RAISE EXCEPTION 'R6 original D5 adoption is immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
""")
    op.execute('CREATE TRIGGER r6_preserve_adoption BEFORE UPDATE ON capa_d5_measures FOR EACH ROW EXECUTE FUNCTION r6_preserve_adoption()')
    op.execute("""
CREATE FUNCTION r6_complete_candidate_sources() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE candidate uuid; expected integer; actual bigint;
BEGIN
  candidate := NEW.candidate_id;
  SELECT source_count INTO expected FROM capa_d4_candidates WHERE candidate_id=candidate;
  SELECT count(*) INTO actual FROM capa_d4_candidate_sources WHERE candidate_id=candidate;
  IF expected IS DISTINCT FROM actual THEN
    RAISE EXCEPTION 'R6 candidate sources incomplete' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$
""")
    for table in ('capa_d4_candidates', 'capa_d4_candidate_sources'):
        op.execute(f'CREATE CONSTRAINT TRIGGER r6_complete_candidate_sources AFTER INSERT ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION r6_complete_candidate_sources()')
    op.execute("""
CREATE FUNCTION r6_root_history_order() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_no bigint;
BEGIN
  -- Serialize before querying recorded bodies. A competing insert waiting on
  -- this parent rechecks committed history after acquiring the same lock.
  PERFORM report_id FROM capa_eightd WHERE report_id=NEW.report_id FOR UPDATE;
  SELECT revision_no INTO current_no FROM capa_d4_root_cause_revisions
    WHERE revision_id=NEW.revision_id AND report_id=NEW.report_id;
  IF current_no IS NULL OR EXISTS (
      SELECT 1 FROM capa_r6_root_revision_bodies b
      JOIN capa_d4_root_cause_revisions r ON r.revision_id=b.revision_id
      WHERE b.report_id=NEW.report_id AND r.revision_no > current_no) THEN
    RAISE EXCEPTION 'R6 older root bodies cannot be backfilled' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
""")
    op.execute('CREATE TRIGGER r6_root_history_order BEFORE INSERT ON capa_r6_root_revision_bodies FOR EACH ROW EXECUTE FUNCTION r6_root_history_order()')
    op.execute("""
CREATE FUNCTION r6_complete_root_sources() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_body record; actual bigint; previous_no bigint; current_no bigint; expected_previous uuid;
BEGIN
  SELECT * INTO STRICT current_body FROM capa_r6_root_revision_bodies WHERE revision_id=NEW.revision_id;
  SELECT count(*) INTO actual FROM capa_r6_root_revision_sources WHERE revision_id=NEW.revision_id;
  IF current_body.source_count <> actual THEN
    RAISE EXCEPTION 'R6 root sources incomplete' USING ERRCODE='23514';
  END IF;
  SELECT revision_no INTO current_no FROM capa_d4_root_cause_revisions WHERE revision_id=NEW.revision_id;
  SELECT b.revision_id INTO expected_previous FROM capa_r6_root_revision_bodies b
    JOIN capa_d4_root_cause_revisions r ON r.revision_id=b.revision_id
    WHERE b.report_id=current_body.report_id AND r.revision_no < current_no
    ORDER BY r.revision_no DESC LIMIT 1;
  IF current_body.predecessor_id IS DISTINCT FROM expected_previous THEN
    RAISE EXCEPTION 'R6 root predecessor cannot be skipped' USING ERRCODE='23514';
  END IF;
  IF current_body.predecessor_id IS NOT NULL THEN
    SELECT revision_no INTO previous_no FROM capa_d4_root_cause_revisions WHERE revision_id=current_body.predecessor_id;
    IF previous_no >= current_no OR EXISTS (
        SELECT source_id FROM capa_r6_root_revision_sources WHERE revision_id=current_body.predecessor_id
        EXCEPT SELECT source_id FROM capa_r6_root_revision_sources WHERE revision_id=NEW.revision_id) THEN
      RAISE EXCEPTION 'R6 root sources cannot be subtracted' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END $$
""")
    for table in ('capa_r6_root_revision_bodies', 'capa_r6_root_revision_sources'):
        op.execute(f'CREATE CONSTRAINT TRIGGER r6_complete_root_sources AFTER INSERT ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION r6_complete_root_sources()')


def downgrade():
    connection = op.get_bind()
    # All guards run before any destructive DDL, including source-only evidence.
    for table in TABLES:
        if connection.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')):
            raise RuntimeError('R6 evidence exists; downgrade refused')
    op.execute('DROP TRIGGER r6_preserve_adoption ON capa_d5_measures')
    for table in reversed(TABLES):
        op.drop_table(table)
    for function in ('r6_complete_root_sources', 'r6_root_history_order', 'r6_complete_candidate_sources', 'r6_preserve_adoption',
                     'r6_validate_correction', 'r6_validate_origin', 'r6_candidate_transition',
                     'r6_material_monotonic', 'r6_immutable_history'):
        op.execute(f'DROP FUNCTION {function}()')
    for table, name, columns in reversed(EXISTING_UNIQUES):
        op.drop_constraint(name, table, type_='unique')
