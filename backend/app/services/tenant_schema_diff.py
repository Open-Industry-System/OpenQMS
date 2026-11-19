"""Object-level tenant schema parity against an independently migrated public schema."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.tenant_utils import strict_tenant_search_path_sql
from app.core.tenant_sql_tokens import rewrite_qualifiers, scan_sql

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "alembic_tenant/snapshot/manifest.json"
EXCLUDED = frozenset({"tenants", "tenant_migrations", "tenant_attachment_storage_disposals", "platform_login_attempts", "platform_admin_users", "reference_templates",
                      "alembic_version", "tenant_schema_version"})


@dataclass(frozen=True)
class SchemaDifference:
    object_type: str
    object_key: str
    expected: str
    actual: str


def load_snapshot_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def verify_snapshot_checksum(manifest: dict) -> None:
    from alembic_tenant.snapshot.business_20260927 import DDL
    digest = hashlib.sha256("\n".join(DDL).encode()).hexdigest()
    if digest != manifest.get("sha256") or manifest.get("pg_major") != 15:
        raise ValueError("Tenant baseline checksum or PostgreSQL major mismatch")


def _normalize_varchar_arrays(source: str) -> str:
    """Normalize PG15 dump/restore's varchar[]→text[] cast at token boundaries."""
    tokens = scan_sql(source)
    values = [t.text for t in tokens]
    def next_code(i):
        while i < len(tokens) and tokens[i].kind in {"space", "comment"}:
            i += 1
        return i

    for i, token in enumerate(tokens):
        if token.identifier != "array":
            continue
        opening = next_code(i + 1)
        if opening >= len(tokens) or values[opening] != "[":
            continue
        depth, closing = 1, opening + 1
        while closing < len(tokens) and depth:
            if values[closing] == "[": depth += 1
            if values[closing] == "]": depth -= 1
            closing += 1
        if depth:
            continue
        suffix = []
        pos = next_code(closing)
        for part in (":", ":", "text", "[", "]"):
            if pos >= len(tokens) or values[pos].lower() != part:
                break
            suffix.append(pos)
            pos = next_code(pos + 1)
        if len(suffix) != 5:
            continue
        casts = []
        for j in range(opening + 1, closing - 1):
            if values[j] != ":":
                continue
            second = next_code(j + 1)
            typ = next_code(second + 1)
            varying = next_code(typ + 1)
            if (second < len(tokens) and values[second] == ":" and typ < len(tokens)
                    and tokens[typ].identifier == "character" and varying < len(tokens)
                    and tokens[varying].identifier == "varying"):
                casts.append(varying)
        if casts:
            for j in casts:
                values[j] += "::text"
            for j in suffix:
                values[j] = ""
    return "".join(values)


def _normalize(value: object, schema: str) -> str:
    result = str(value) if value is not None else "<null>"
    # pg_dump recreates varchar literal arrays with equivalent element casts.
    # Only rewrite SQL tokens, never quoted literals containing array-like text.
    result = _normalize_varchar_arrays(result)
    return rewrite_qualifiers(result, schema, shared_public=frozenset({"vector", "vector_cosine_ops"}),
                              canonicalize_shared_digest=True, collapse_space=True)


async def _objects(connection: AsyncConnection, schema: str) -> dict[tuple[str, str], str]:
    query = text("""
        SELECT 'table' AS kind, c.relname::text AS key, c.relkind::text AS definition
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'column', c.relname||'.'||a.attname,
          pg_catalog.format_type(a.atttypid,a.atttypmod)||'|'||a.attnotnull::text||'|'||
          coalesce(pg_get_expr(d.adbin,d.adrelid),'')||'|'||a.attidentity::text||'|'||a.attgenerated::text
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'constraint', c.relname||'.'||con.conname, con.contype::text||'|'||
          pg_get_constraintdef(con.oid,true)||'|'||con.condeferrable::text||'|'||con.condeferred::text
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'index', tab.relname||'.'||idx.relname, pg_get_indexdef(idx.oid)||'|'||
            i.indisvalid::text||'|'||i.indisready::text
        FROM pg_index i JOIN pg_class idx ON idx.oid=i.indexrelid
        JOIN pg_class tab ON tab.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=tab.relnamespace
        WHERE n.nspname=:schema AND tab.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'function', p.proname||'('||pg_get_function_identity_arguments(p.oid)||')', pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname=:schema AND NOT EXISTS (
            SELECT 1 FROM pg_depend d WHERE d.objid=p.oid AND d.classid='pg_proc'::regclass AND d.deptype='e')
        UNION ALL
        SELECT 'trigger', c.relname||'.'||t.tgname, pg_get_triggerdef(t.oid,true)
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND NOT t.tgisinternal AND c.relname <> ALL(:excluded)
        UNION ALL
        SELECT 'text_search_config', cfg.cfgname, cfg.cfgparser::regproc::text||'|'||
            coalesce((SELECT string_agg(m.maptokentype::text||':'||m.mapseqno::text||':'||dict.dictname,
                                        ',' ORDER BY m.maptokentype,m.mapseqno)
                      FROM pg_ts_config_map m JOIN pg_ts_dict dict ON dict.oid=m.mapdict
                      WHERE m.mapcfg=cfg.oid),'')
        FROM pg_ts_config cfg JOIN pg_namespace n ON n.oid=cfg.cfgnamespace
        WHERE n.nspname=:schema
    """)
    rows = (await connection.execute(query, {"schema": schema, "excluded": list(EXCLUDED)})).all()
    return {(kind, key): _normalize(definition, schema) for kind, key, definition in rows}


async def compare_business_schema(connection: AsyncConnection, reference_schema: str, tenant_schema: str,
                                  manifest: dict, *, baseline_only: bool = False, predecessor: str | None = None) -> list[SchemaDifference]:
    if reference_schema != "public":
        raise ValueError("Only canonical public schema is a supported reference")
    strict_tenant_search_path_sql(tenant_schema)
    verify_snapshot_checksum(manifest)
    reference = await _objects(connection, reference_schema)
    if baseline_only or predecessor is not None:
        iqc_fact_objects = {
            ("function", "iqc_association_write_fence()"),
            ("trigger", "iqc_inspections.iqc_association_write_fence"),
            ("trigger", "supplier_scars.iqc_association_write_fence"),
            ("trigger", "capa_eightd.iqc_association_write_fence"),
            ("trigger", "agent_results.iqc_investigation_result_guard"),
            ("function", "iqc_investigation_result_guard()"),
            ("function", "iqc_investigation_ledger_guard()"),
            ("column", "agent_tasks.task_type"),
            ("column", "agent_tasks.target_iqc_inspection_id"),
            ("constraint", "agent_tasks.ck_agent_task_typed_anchor"),
            ("constraint", "agent_tasks.fk_agent_task_iqc_factory"),
            ("column", "iqc_inspections.identity_generation"),
            ("column", "iqc_inspections.inspection_revision"),
            ("constraint", "iqc_inspections.uq_iqc_inspection_factory"),
            ("index", "iqc_inspections.uq_iqc_inspection_factory"),
            ("trigger", "iqc_inspections.iqc_fact_revision_guard"),
            ("trigger", "iqc_inspection_items.iqc_item_fact_revision"),
            ("trigger", "iqc_item_measurements.iqc_measurement_fact_revision"),
            ("function", "iqc_fact_revision_guard()"),
            ("function", "iqc_revise_from_detail()"),
        }
        anchor_column = ("column", "agent_tasks.target_capa_id")
        if reference.get(anchor_column) == "uuid|false|||":
            reference[anchor_column] = "uuid|true|||"
        iqc_tables = {"agent_iqc_investigation_bindings", "agent_iqc_investigation_receipts"}
        reference = {key: value for key, value in reference.items()
                     if key not in iqc_fact_objects and key[1].split(".")[0] not in iqc_tables}
    if predecessor == "tv025_r7_pfmea_impact":
        predecessor = None
    if baseline_only or predecessor is not None:
        r7_tables = {
            "agent_pfmea_impact_bindings", "agent_pfmea_impact_receipts",
            "agent_pfmea_impact_result_receipts",
        }
        r7_objects = {
            ("column", "fmea_documents.r7_scope_generation"),
            ("column", "fmea_versions.r7_approved_scope_generation"),
            ("trigger", "fmea_documents.r7_impact_target_generation"),
            ("trigger", "fmea_versions.r7_impact_approval_generation"),
            ("function", "r7_impact_ledger_guard()"),
            ("trigger", "agent_results.r7_impact_result_guard"),
            ("function", "r7_impact_result_guard()"),
            ("function", "r7_impact_target_generation()"),
            ("function", "r7_impact_approval_generation()"),
        }
        # Filter the reviewed public delta only; partially applied tenant DDL
        # must still be visible as unexpected objects and block the upgrade.
        reference = {key: value for key, value in reference.items()
                     if key[1].split(".")[0] not in r7_tables and key not in r7_objects}
    if predecessor == 'tv024_r6_local_capa_sources':
        predecessor = None
    if baseline_only or predecessor is not None:
        omitted={('column','capa_r6_local_sources.source_capa_id'),('column','capa_r6_local_sources.source_capa_created_at'),
                 ('constraint','capa_r6_local_sources.ck_r6_local_capa_identity')}
        reference={key:value for key,value in reference.items() if key not in omitted}
        key=('constraint','capa_r6_local_sources.ck_r6_local_source')
        if key in reference and "'capa'" in reference[key]:
            value=reference[key];position=value.index("'capa'")
            comma=value.rfind(',',0,position);closing=value.find(']',position)
            if comma<0 or closing<0:raise ValueError('Unexpected local source enum catalog')
            reference[key]=value[:comma]+value[closing:]
    if predecessor == 'tv023_r6_legacy_capture': predecessor=None
    if baseline_only or predecessor is not None:
        reference={key:value for key,value in reference.items()
            if key[1].split('.')[0]!='capa_r6_legacy_captures' and key!=('function','r6_reject_legacy_capture_mutation()')}
    if predecessor == 'tv022_r6_local_snapshot': predecessor=None
    if baseline_only or predecessor is not None:
        witness_objects={('column','capa_r6_local_revisions.root_snapshot_revision_id'),
            ('constraint','capa_r6_local_revisions.fk_r6_local_snapshot_root'),
            ('constraint','capa_r6_local_revisions.ck_r6_local_snapshot_count'),
            ('constraint','capa_r6_local_revisions.r6_validate_local_snapshot_witness'),
            ('trigger','capa_r6_local_revisions.r6_validate_local_snapshot_witness'),
            ('function','r6_validate_local_snapshot_witness()')}
        reference={key:value for key,value in reference.items() if key not in witness_objects}
        key=('constraint','capa_r6_local_revisions.ck_r6_local_inputs')
        if key in reference:reference[key]=reference[key].replace('source_count >= 0','source_count > 0')
    if predecessor == 'tv021_r6_manual_receipts': predecessor=None
    if baseline_only or predecessor is not None:
        reference={key:value for key,value in reference.items() if key[1].split('.')[0]!='capa_r6_manual_decision_receipts' and key!=('function','r6_validate_manual_decision_receipt()')}
    if predecessor == 'tv020_r6_local_closure': predecessor=None
    if baseline_only or predecessor is not None:
        local_tables={'capa_r6_local_revisions','capa_r6_local_sources'}
        reference={key:value for key,value in reference.items() if key[1].split('.')[0] not in local_tables
            and key not in {('column','capa_docg_analysis.analysis_method'),('constraint','capa_docg_analysis.ck_docg_analysis_method'),('trigger','capa_docg_analysis.r6_complete_local_record'),('constraint','capa_docg_analysis.r6_complete_local_record'),('function','r6_complete_local_record()')}}
        old_done="c|CHECK (status::text <> 'done'::text OR affected_docs IS NOT NULL AND analysis_input_hash IS NOT NULL AND llm_available = true AND completed_at IS NOT NULL)|false|false"
        # Historical comparison restores the reviewed pre-020 constraint;
        # never filters tenant objects, so partial deltas remain visible.
        key=('constraint','capa_docg_analysis.chk_docg_analysis_done_complete')
        if key in reference: reference[key]=old_done
    if predecessor == 'tv019_r6_verify_origins': predecessor=None
    if baseline_only or predecessor is not None:
        verification_objects = {('column','capa_root_cause_verification.r6_source_origins'),
            ('trigger','capa_root_cause_verification.r6_retain_verification_origins'),
            ('function','r6_retain_verification_origins()'), ('function','r6_verification_ref_origin(ref jsonb)')}
        reference = {key:value for key,value in reference.items() if key not in verification_objects}
    if predecessor == 'tv018_r6_d4_withdraw':
        predecessor = None
    if baseline_only or predecessor is not None:
        reference = {key: value for key, value in reference.items()
            if key[1].split('.')[0] != 'capa_d4_candidate_withdrawals' and key != ('function', 'r6_validate_d4_withdrawal()')}
    if predecessor == 'tv017_r6_d4_inputs':
        predecessor = None
    if baseline_only or predecessor is not None:
        input_tables = {'agent_d4_input_receipts', 'agent_d4_input_receipt_sources', 'agent_d4_command_inputs'}
        reference = {key: value for key, value in reference.items()
            if key[1].split('.')[0] not in input_tables and key != ('function', 'r6_complete_d4_inputs()')}
    if predecessor == 'tv016_r6_source_epoch':
        predecessor = None
    if baseline_only or predecessor is not None:
        epoch_objects = {('column', 'capa_r6_source_origins.source_version_counter'),
            ('constraint', 'capa_r6_source_origins.ck_r6_source_version_counter'),
            ('trigger', 'fmea_documents.r6_fmea_source_epoch'),
            ('function', 'r6_fmea_source_epoch()')}
        reference = {key: value for key, value in reference.items() if key not in epoch_objects}
    if predecessor == 'tv015_r6_entry_contracts':
        # This predecessor already owns ALL R6 contracts. Only the new epoch
        # delta is absent; partial tenant deltas remain visible and fail closed.
        predecessor = None
    if baseline_only or predecessor is not None:
        # Reviewed R6 additions are filtered only from the canonical reference.
        # A historical tenant with even one partial R6 object remains different.
        r6_tables = {'capa_r6_material_versions', 'capa_r6_entry_switches', 'capa_r6_report_snapshots',
                     'capa_r6_source_origins', 'agent_d4_candidate_commands',
                     'agent_d4_candidate_checkpoint_positions', 'capa_d4_candidates',
                     'capa_d4_candidate_sources', 'capa_r6_root_revision_bodies',
                     'capa_r6_root_revision_sources', 'capa_d5_measure_revisions',
                     'capa_r6_staff_receipts', 'capa_r6_root_delivery_bindings'}
        r6_functions = {'r6_immutable_history', 'r6_material_monotonic', 'r6_candidate_transition',
                        'r6_validate_origin', 'r6_validate_correction', 'r6_preserve_adoption',
                        'r6_complete_candidate_sources', 'r6_complete_root_sources', 'r6_root_history_order'}
        r6_existing = {
            ('constraint', 'agent_tasks.uq_r6_task_report'), ('index', 'agent_tasks.uq_r6_task_report'),
            ('constraint', 'agent_runs.uq_r6_run_task'), ('index', 'agent_runs.uq_r6_run_task'),
            ('constraint', 'agent_task_messages.uq_r6_message_task'), ('index', 'agent_task_messages.uq_r6_message_task'),
            ('constraint', 'capa_d4_root_cause_revisions.uq_r6_root_report'), ('index', 'capa_d4_root_cause_revisions.uq_r6_root_report'),
            ('constraint', 'agent_d5_basis_receipts.uq_r6_basis_root'), ('index', 'agent_d5_basis_receipts.uq_r6_basis_root'),
            ('constraint', 'agent_d4_recovery_checkpoints.uq_r6_checkpoint_task'), ('index', 'agent_d4_recovery_checkpoints.uq_r6_checkpoint_task'),
            ('trigger', 'capa_d5_measures.r6_preserve_adoption'),
        }
        reference = {key: value for key, value in reference.items()
                     if key not in r6_existing
                     and not (key[0] == 'function' and key[1].split('(', 1)[0] in r6_functions)
                     and not (key[0] in {'table', 'column', 'constraint', 'index', 'trigger'}
                              and key[1].split('.', 1)[0] in r6_tables)}
    has_responses = predecessor == 'tv014_r5_responses'
    if has_responses:
        # The full R5 merge shape is identical apart from the explicit protocol.
        predecessor = 'tv013_r5_main_merge'
    # Only historical reference shapes exclude the two reviewed later columns.
    # Current parity and the tenant side remain complete and fail closed.
    if baseline_only or (predecessor is not None and predecessor not in {"tv007_characteristic_refs", "tv009_r4b_main_merge", "tv010_r5_d5_proposals", "tv011_r5_d5_basis", "tv012_r5_models", "tv010_refresh_sessions", "tv013_r5_main_merge"}):
        later_columns = {("column", "control_plan_items.source_characteristic_ref"),
                         ("column", "special_characteristics.source_characteristic_id")}
        reference = {key: value for key, value in reference.items() if key not in later_columns}
    if baseline_only:
        # R1 adds tables only: retain every frozen table-owned object plus the
        # reviewed functions/configuration. The tenant side is never filtered,
        # so extra or partially applied delta objects are still rejected.
        keys = set(manifest["object_keys"])
        tables = {key.removeprefix("TABLE:") for key in keys if key.startswith("TABLE:")}
        reference = {key: value for key, value in reference.items()
                     if (key[0] in {"table", "column", "constraint", "index", "trigger"}
                         and key[1].split(".", 1)[0] in tables)
                     or (key[0] == "function" and f"FUNCTION:{key[1]}" in keys)
                     or (key[0] == "text_search_config" and f"TEXT SEARCH CONFIGURATION:{key[1]}" in keys)}
    if predecessor is not None:
        known = {"tv002_agent_task_core", "tv003_agent_readonly_delivery", "tv004_agent_readonly_controls", "tv005_agent_task_attachments", "tv006_agent_read_tasks", "tv007_characteristic_refs", "tv007_d4_text_delivery", "tv008_d4_recovery", "tv009_r4b_main_merge", "tv010_r5_d5_proposals", "tv011_r5_d5_basis", "tv012_r5_models", "tv010_refresh_sessions", "tv013_r5_main_merge"}
        if predecessor not in known or baseline_only:
            raise ValueError("Unsupported schema predecessor")
        # Filter only the public reference; tenant objects remain fully visible.
        recovery_tables = {"agent_d4_recovery_checkpoints", "agent_d4_recovery_restarts", "agent_d4_task_parent_grants"}
        text_tables = {"capa_d4_root_cause_revisions", "capa_d4_root_cause_source_proofs", "agent_restricted_projection_receipts", "agent_plugin_derived_source_scopes", "agent_task_derived_source_scopes", "agent_task_source_requests"}
        added_tables = set() if predecessor in {"tv008_d4_recovery", "tv009_r4b_main_merge", "tv010_r5_d5_proposals", "tv011_r5_d5_basis", "tv012_r5_models", "tv010_refresh_sessions", "tv013_r5_main_merge"} else recovery_tables.copy()
        if predecessor not in {'tv010_refresh_sessions', 'tv013_r5_main_merge'}:
            added_tables.add('user_refresh_sessions')
        if predecessor not in {'tv012_r5_models', 'tv013_r5_main_merge'}:
            added_tables |= {'agent_model_deployments', 'agent_task_model_bindings'}
        if predecessor not in {'tv011_r5_d5_basis', 'tv012_r5_models', 'tv013_r5_main_merge'}:
            added_tables |= {'agent_d5_basis_receipts', 'agent_d5_command_basis'}
        if predecessor not in {'tv010_r5_d5_proposals', 'tv011_r5_d5_basis', 'tv012_r5_models', 'tv013_r5_main_merge'}:
            added_tables |= {'agent_d5_commands', 'capa_d5_withdrawals', 'capa_d5_proposal_sources', 'agent_d5_checkpoint_positions', 'capa_d5_proposals', 'capa_d5_staff_receipts', 'capa_d5_measures'}
        if predecessor not in {"tv007_d4_text_delivery", "tv008_d4_recovery", "tv009_r4b_main_merge", "tv010_r5_d5_proposals", "tv011_r5_d5_basis", "tv012_r5_models", "tv010_refresh_sessions", "tv013_r5_main_merge"}:
            added_tables |= text_tables
        if predecessor not in {"tv006_agent_read_tasks", "tv007_characteristic_refs", "tv007_d4_text_delivery", "tv008_d4_recovery", "tv009_r4b_main_merge", "tv010_r5_d5_proposals", "tv011_r5_d5_basis", "tv012_r5_models", "tv010_refresh_sessions", "tv013_r5_main_merge"}:
            added_tables.add("agent_read_tasks")
        if predecessor not in {"tv005_agent_task_attachments", "tv006_agent_read_tasks", "tv007_characteristic_refs", "tv007_d4_text_delivery", "tv008_d4_recovery", "tv009_r4b_main_merge", "tv010_r5_d5_proposals", "tv011_r5_d5_basis", "tv012_r5_models", "tv010_refresh_sessions", "tv013_r5_main_merge"}:
            added_tables.add("agent_task_attachments")
        if predecessor in {"tv002_agent_task_core", "tv003_agent_readonly_delivery"}:
            added_tables |= {"agent_task_controls", "agent_readonly_checkpoints",
                             "agent_checkpoint_receipts", "agent_task_updates"}
        added_objects = {
            ("column", "agent_model_deployments.api_protocol"),
            ("constraint", "agent_model_deployments.ck_model_deployment_api_protocol"),
        }
        if has_responses:
            added_objects = set()
        if predecessor in {"tv002_agent_task_core", "tv003_agent_readonly_delivery"}:
            added_objects |= {
                ("column", "agent_runs.resume_checkpoint_id"),
                ("constraint", "agent_runs.fk_agent_run_resume_checkpoint"),
            }
        if predecessor == "tv002_agent_task_core":
            added_tables |= {"agent_projection_receipts", "agent_run_events", "agent_results",
                             "agent_event_receipts", "agent_result_receipts"}
            added_objects |= {
                ("column", "agent_runs.claim_key"),
                ("column", "agent_runs.lease_expires_at"),
                ("index", "agent_runs.uq_agent_run_installation_claim"),
                ("column", "agent_task_messages.delivery_batch_id"),
                ("column", "agent_task_messages.delivery_epoch"),
            }
        reference = {key: value for key, value in reference.items()
                     if key not in added_objects and not (predecessor not in {'tv012_r5_models', 'tv013_r5_main_merge'} and key[0] == 'function' and key[1].split('(', 1)[0] in {'r5_immutable_deployment', 'r5_immutable_task_model'}) and not (
                         key[0] in {"table", "column", "constraint", "index", "trigger"}
                         and key[1].split(".", 1)[0] in added_tables)}
    tenant = await _objects(connection, tenant_schema)
    return [SchemaDifference(kind, key, reference.get((kind, key), "<missing>"),
                             tenant.get((kind, key), "<missing>"))
            for kind, key in sorted(reference.keys() | tenant.keys()) if reference.get((kind, key)) != tenant.get((kind, key))]
