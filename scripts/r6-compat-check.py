#!/usr/bin/env python3
"""Check rehearsal evidence without granting production release authority.

All references are content addressed. This supplementary checker deliberately
keeps the original C9 pytest failure distinct from its reviewed composed result.
It never edits the frozen application, switch documents, or database.
"""

import argparse
import hashlib
import json
import hmac
import math
from urllib.parse import urlsplit
import ipaddress
from datetime import datetime
from uuid import UUID
import os
from pathlib import Path
import re
import subprocess


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def verified_bytes(value):
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("content-addressed evidence reference required")
    path = Path(value["path"])
    if not path.is_absolute() or not re.fullmatch("[0-9a-f]{64}", value["sha256"]):
        raise ValueError("absolute evidence path and exact digest required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != value["sha256"]:
        raise ValueError("evidence bytes changed")
    return data


def load_reference(value):
    return json.loads(verified_bytes(value))


def _validate_certificate(value):
    if set(value) != {
        "kind",
        "status",
        "production_authorized",
        "c9",
        "c9_snapshot",
        "c9_readonly_manifest",
        "original_failed_receipt",
        "c10",
        "internal_contracts",
        "audit_baseline",
        "generation_off_probe",
    }:
        raise ValueError("complete exact rehearsal certificate fields required")
    if (
        value.get("kind") != "r6.compatibility-rehearsal.v1"
        or value.get("status") != "PASS"
    ):
        raise ValueError("executed compatibility certificate required")
    if value.get("production_authorized") is not False:
        raise ValueError("rehearsal cannot authorize production")
    c9 = load_reference(value["c9"])
    if (
        c9.get("status") != "COMPOSED_PASS"
        or c9.get("original_live_status") != "FAILED"
        or c9.get("evidence_method") != "COMPOSED_SAME_REPORT_SEQUENTIAL"
    ):
        raise ValueError("honest reviewed composed C9 required")
    original = load_reference(value["original_failed_receipt"])
    # Preserve the original receipt independently; a composed PASS is not a
    # rewrite of a failed fresh live pytest receipt.
    if (
        original.get("status") != "FAILED"
        or original.get("exit_code") != 1
        or original.get("failed") != 1
        or original.get("passed") != 0
    ):
        raise ValueError("original failed C9 cannot be relabelled")
    manifest = load_reference(value["c9_readonly_manifest"])
    if (
        value["c9_readonly_manifest"]["sha256"]
        != c9["readonly_final"]["manifest_sha256"]
        or value["original_failed_receipt"]["sha256"]
        not in manifest["external_evidence"].values()
    ):
        raise ValueError("composed C9 must bind its actual original failed receipt")
    c10 = load_reference(value["c10"])
    if c10.get("status") != "SCENARIO_ASSERTIONS_PASSED" or c10.get(
        "report_id"
    ) != c9.get("report_id"):
        raise ValueError("same-report C10 execution required")
    if (
        c10.get("new_main_model_calls") != 0
        or c10.get("paid_provider_calls") != 0
        or c10.get("provider_credential_loaded") is not False
    ):
        raise ValueError(
            "new main/provider activity invalidates read-only compatibility evidence"
        )
    processes = c10.get("processes", [])
    if len(processes) != 2 or {p["mode"] for p in processes} != {
        "candidate",
        "compatible",
    }:
        raise ValueError("two executed deployment modes required")
    if len({p["pid"] for p in processes}) != 2 or any(
        p["exit"] not in {0, -15} for p in processes
    ):
        raise ValueError("distinct drained processes required")
    if [p["mode"] for p in processes] != ["candidate", "compatible"] or [
        p["generation_enabled"] for p in processes
    ] != [True, False]:
        raise ValueError("registered compatible generation must be disabled")
    if len({p["configuration"]["sha256"] for p in processes}) != 2:
        raise ValueError("two exact registered deployment configurations required")
    for p in processes:
        configuration = load_reference(p["configuration"])
        if (configuration.get("R6_GENERATION_ENABLED", "true") == "true") != p[
            "generation_enabled"
        ]:
            raise ValueError("generation configuration mismatch")
    if any(not re.fullmatch("[0-9a-f]{64}", p["build"]) for p in processes):
        raise ValueError("exact executable artifact digest required")
    snapshots = [load_reference(p["snapshot"]) for p in processes]
    keys = ("current", "history", "review", "local", "decision", "current_sources")
    if any(snapshots[0][key] != snapshots[1][key] for key in keys):
        raise ValueError("same data current/history/source/audit mismatch")
    original_snapshot = load_reference(value["c9_snapshot"])
    if value["c9_snapshot"]["sha256"] != c9["readonly_final"]["evidence_sha256"] or any(
        original_snapshot[key] != snapshots[0][key] for key in keys
    ):
        raise ValueError("original accepted C9 material changed")
    baseline = validate_pre_attempt(
        value["audit_baseline"],
        value["c9_snapshot"],
        snapshots[0]["original_switch"]["target"],
    )
    for snapshot in snapshots:
        require_same_database(original_snapshot["database"], snapshot["database"])
    if snapshots[0]["current"]["status"] != "D8_CLOSURE":
        raise ValueError("closed original report must stay closed")
    controls = c10["control_checks"]
    sources = c10["source_checks"]
    if len(controls) != 4:
        raise ValueError("exact main correction and terminal controls required")
    validate_generation_off_probe(value["generation_off_probe"], processes)
    for mode in ("candidate", "compatible"):
        editable = [
            c for c in controls if c["mode"] == mode and "concurrent_statuses" in c
        ]
        terminal = [
            c
            for c in controls
            if c["mode"] == mode and "terminal_correction_status" in c
        ]
        if (
            len(editable) != 1
            or sorted(editable[0]["concurrent_statuses"]) != [200, 409]
            or editable[0]["retry_status"] != 200
            or editable[0].get("unversioned_status") not in {409, 422}
            or editable[0].get("manual_status") != 200
            or editable[0].get("stale_status") != 409
            or editable[0].get("revoked_status") != 404
            or not editable[0]["adopted_preserved"]
        ):
            raise ValueError("genuine concurrent correction/retry evidence required")
        if (
            len(terminal) != 1
            or terminal[0]["terminal_correction_status"] != 409
            or terminal[0]["view_correction_status"] != 403
        ):
            raise ValueError("editor terminal and viewer denial required")
        required = {
            "",
            "/d5-measures",
            "/d5-proposals",
            "/root-cause-verifications",
            "/local-closure",
            "/outcome-review",
            "/d5-measures/" + snapshots[0]["measure_id"] + "/corrections",
            "/sources/d5-proposal/" + snapshots[0]["a"],
            "/sources/d5-proposal/" + snapshots[0]["b"],
            "/sources/d5-measure/" + snapshots[0]["measure_id"],
            "/ppt-exports/" + snapshots[0]["existing_export"]["export_id"],
            "d4-fmea-recommendations",
            "d5-fmea-recommendations",
            "draft/d4",
            "draft/d5",
        }
        actual = [c for c in sources if c["mode"] == mode]
        for scenario in actual:
            if scenario["path"].startswith(("draft/", "d4-fmea", "d5-fmea")):
                if scenario["status"] != 410 or scenario["response"] != {
                    "detail": "CAPA_ENTRY_RETIRED_REFRESH_REPORT"
                }:
                    raise ValueError("retired entry returned non-retired result")
            elif scenario["status"] == 200:
                body = scenario["response"]
                if scenario["path"] not in {
                    "/d5-measures",
                    "/d5-proposals",
                    "/root-cause-verifications",
                } or not (
                    body == []
                    or (
                        body["items"] == []
                        and body["total"] == 0
                        and body["page"] == 1
                        and body["page_size"] == 20
                        and set(body)
                        == (
                            {"items", "total", "page", "page_size", "legacy_text"}
                            if scenario["path"] == "/d5-measures"
                            else {"items", "total", "page", "page_size"}
                        )
                        and body.get("legacy_text")
                        in {None, snapshots[0]["current"]["d5_correction"]}
                    )
                ):
                    raise ValueError("revoked source body or count leaked")
            elif scenario["status"] in {403, 404}:
                body = scenario["response"]
                witnesses = [
                    snapshots[0]["current"]["d4_root_cause"],
                    snapshots[0]["history"]["adopted_text"],
                    snapshots[0]["history"]["final_text"],
                ]
                witnesses.extend(
                    row["original_text"]
                    for row in snapshots[0]["immutable_original_model"][
                        "proposal_bodies"
                    ]
                )
                safe = {
                    "R6 item unavailable",
                    "D4_MATERIAL_UNAVAILABLE",
                    "D5_MATERIAL_UNAVAILABLE",
                    "8D report not found",
                    "CAPA_OUTCOME_REVIEW_ACCESS_DENIED",
                    "CAPA_OUTCOME_REVIEW_UNAVAILABLE",
                    "PPT_MATERIAL_UNAVAILABLE",
                }
                if (
                    set(body) != {"detail"}
                    or body["detail"] not in safe
                    or any(
                        text and text in json.dumps(body, ensure_ascii=False)
                        for text in witnesses
                    )
                ):
                    raise ValueError("protected source body leaked with denial status")
            else:
                raise ValueError("source counterexample did not actually deny")
        if {c["path"] for c in actual} != required or len(actual) != len(required):
            raise ValueError(
                "complete exact source and retired-entry inventory required"
            )
    before = baseline["database"]
    for mode, snapshot in zip(("candidate", "compatible"), snapshots):
        requests = [
            row
            for row in sources
            if row["mode"] == mode and row["path"].startswith("draft/")
        ]
        require_draft_audit_transition(
            before["audit"], snapshot["database"]["audit"], requests, c10["report_id"]
        )
        before = snapshot["database"]
    for process in processes:
        registry = load_reference(process["authority"])
        key = os.environ.get("R6_SWITCH_AUTHORITY_KEY", "")
        if not key or not hmac.compare_digest(
            registry["signature"],
            hmac.new(
                key.encode(), _digest(registry["record"]).encode(), hashlib.sha256
            ).hexdigest(),
        ):
            raise ValueError("actual process registry signature invalid")
        target = registry["record"]["target"]
        expected_target = snapshots[0]["original_switch"]["target"]
        if (
            target != expected_target
            or process["build"]
            != target[
                "candidate_build"
                if process["mode"] == "candidate"
                else "compatible_build"
            ]
        ):
            raise ValueError("process target/schema/owner/config/build changed")
        artifact = load_reference(
            registry["record"]["build_artifacts"][process["build"]]
        )
        config_path = registry["record"]["config_file"]
        configuration = json.loads(Path(config_path).read_text())
        if (
            reference(config_path)["sha256"] != target["config_digest"]
            or artifact["config_digest"] != target["config_digest"]
            or _digest(artifact) != process["build"]
            or artifact["schema_heads"]
            != [target["public_head"], target["tenant_head"]]
            or configuration["execution"]["deployment_configurations"][process["mode"]]
            != process["configuration"]
        ):
            raise ValueError(
                "registered executable/schema/deployment config binding differs"
            )
        registration = load_reference(process["registration"])
        if any(
            registration["launch"][key] != artifact[key]
            for key in ("executable", "executable_digest", "config_digest")
        ):
            raise ValueError(
                "actual process executable/configuration differs from frozen artifact"
            )
        instances = registry["record"]["instances"]
        if (
            len(instances) != 1
            or load_reference(instances[0]) != registration["launch"]
        ):
            raise ValueError("unknown or unbound process inventory")
        launch = dict(registration["launch"])
        signature = launch.pop("signature")
        launch_key = os.environ.get("R6_SWITCH_LAUNCH_ATTESTATION_KEY", "")
        if not launch_key or not hmac.compare_digest(
            signature,
            hmac.new(
                launch_key.encode(), _digest(launch).encode(), hashlib.sha256
            ).hexdigest(),
        ):
            raise ValueError("actual process launch signature invalid")
        if (
            registration["launch"]["pid"] != process["pid"]
            or registration["launch"]["build"] != process["build"]
        ):
            raise ValueError("actual registered PID mismatch")
        if (
            registration["status"]["state"] != "switched"
            or registration["status"]["epoch"] != 3
            or registration["accepted_document_digest"]
            != snapshots[0]["original_switch"]["current_accepted_document_digest"]
            or registration["status"]["operation_ref"]
            != snapshots[0]["original_switch"]["operation"]
        ):
            raise ValueError("accepted exercise switch evidence required")
    _internal_contracts(value["internal_contracts"], processes)
    return value


def _signed(value, key_name):
    key = os.environ.get(key_name, "")
    if not key or not hmac.compare_digest(
        value["signature"],
        hmac.new(
            key.encode(), _digest(value["record"]).encode(), hashlib.sha256
        ).hexdigest(),
    ):
        raise ValueError("registered evidence signature invalid")
    return value["record"]


def _contract_group(group, expected, files, build, fixtures):
    receipt = load_reference(group["receipt"])
    if (
        any(
            receipt.get(key) != 0
            for key in (
                "exit_code",
                "skipped",
                "failed",
                "errors",
                "xfailed",
                "xpassed",
            )
        )
        or receipt.get("status") != "PASSED"
    ):
        raise ValueError("complete actual native files must pass without skip or xfail")
    flags = load_reference(group["effective_flags"])
    raw = [
        json.loads(line)
        for line in verified_bytes(group["raw_flags"]).decode().splitlines()
    ]
    if raw != flags:
        raise ValueError("effective flags differ from actual child witness log")
    roster = load_reference(group["roster"])
    nodes = [row["nodeid"] for row in flags]
    if (
        roster.get("status") != "COLLECTED"
        or nodes != roster["nodeids"]
        or len(set(nodes)) != len(nodes)
        or len(nodes) != receipt["passed"]
        or receipt["selected"] != len(nodes)
        or {node.split("::")[0] for node in nodes} != files
    ):
        raise ValueError(
            "actual passed nodes must match full collected file roster exactly"
        )
    if any(
        row["before"] is not expected
        or row["after"] is not expected
        or row["expected"] is not expected
        or row["exception"]
        for row in flags
    ):
        raise ValueError(
            "every node must retain actual registered generation configuration"
        )
    if (
        roster["generation_enabled"] is not expected
        or roster["executable"]["sha256"] != build["executable_digest"]
        or Path(roster["executable"]["path"]).resolve()
        != Path(build["executable"]).resolve()
    ):
        raise ValueError("collected executable/configuration mismatch")
    if (
        roster["mark"]
        != "not ci_browser and not ci_r5_native and not live_provider and not real_scanner"
    ):
        raise ValueError("native roster selection differs")
    if set(roster["source_files"]) != {
        str(Path(build["source_root"]) / "backend" / file) for file in files
    }:
        raise ValueError("complete collected file source hashes required")
    for path, sha in roster["source_files"].items():
        if fixtures.get(path) != sha:
            raise ValueError("native roster source is not frozen")
    if Path(receipt["command"][0]).resolve() != Path(build["executable"]).resolve():
        raise ValueError("native executable differs from registered core")
    if (
        set(
            arg
            for arg in receipt["command"]
            if arg.startswith("tests/") and arg.endswith(".py")
        )
        != files
        or receipt["command"][1] != group["bootstrap"]["path"]
    ):
        raise ValueError("actual gate arguments/bootstrap differ from collected files")
    for name in ("operator", "bootstrap", "collector"):
        if reference(group[name]["path"]) != group[name]:
            raise ValueError("native operator changed")
    return nodes


def _internal_contracts(value, processes):
    contracts = load_reference(value)
    signed = dict(contracts)
    signature = signed.pop("authorization")
    authority_key = os.environ.get("R6_SWITCH_AUTHORITY_KEY", "")
    if not authority_key or not hmac.compare_digest(
        signature,
        hmac.new(
            authority_key.encode(), _digest(signed).encode(), hashlib.sha256
        ).hexdigest(),
    ):
        raise ValueError("internal execution index signature invalid")
    if (
        contracts.get("kind") != "r6.internal-compat-contracts.v1"
        or contracts.get("status") != "PASS"
    ):
        raise ValueError("executed full internal contract index required")
    build = load_reference(contracts["frozen_build"])
    if any(_digest(build) != process["build"] for process in processes):
        raise ValueError("native contracts used a different safety core")
    root = Path(build["source_root"])
    fixed_roots = (
        "backend/app",
        "backend/scripts",
        "backend/alembic/versions",
        "backend/alembic_tenant",
        "frontend/src",
        "sdk",
    )
    current = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for name in fixed_roots
        for p in sorted((root / name).rglob("*"))
        if p.is_file()
        and p.suffix in {".py", ".ts", ".tsx", ".json", ".toml"}
        and not {"__pycache__", "node_modules", ".venv"} & set(p.parts)
    }
    if (
        current != build["source_manifest"]
        or reference(build["executable"])["sha256"] != build["executable_digest"]
    ):
        raise ValueError("complete frozen source/executable changed")
    fixtures = load_reference(contracts["fixture_sources"])
    revision = contracts["fixture_revision"]
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("exact fixture source revision required")
    rows = subprocess.check_output(
        ["git", "ls-tree", "-r", revision, "--", "backend/tests"], cwd=root, text=True
    ).splitlines()
    expected = {}
    for row in rows:
        metadata, path = row.split("\t", 1)
        if (
            not path.endswith(".py")
            or path == "backend/tests/ci/test_r6_release_manifest.py"
        ):
            continue
        data = (root / path).read_bytes()
        if (
            hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            != metadata.split()[2]
        ):
            raise ValueError("native fixture changed from declared execution revision")
        expected[str(root / path)] = hashlib.sha256(data).hexdigest()
    if fixtures != expected:
        raise ValueError("complete native fixture manifest required")
    primary = {
        "tests/capa/" + name + ".py"
        for name in (
            "test_r6_d5_corrections",
            "test_r6_d5_correction_review",
            "test_r6_sources_view",
            "test_r6_draft_release",
            "test_r6_d4_consumers",
            "test_r6_legacy_capture",
            "test_capa_verification_source_ref",
            "test_r6_local_closure",
            "test_r6_manual_doc_gate",
            "test_r6_local_ppt_export",
        )
    }
    source = {
        "tests/capa/test_d4_source_access.py",
        "tests/capa/test_r6_d4_material.py",
    }
    nodes_by_mode = {}
    runs = contracts["runs"]
    if len(runs) != 2 or {run["mode"] for run in runs} != {"candidate", "compatible"}:
        raise ValueError("both native generation configurations required")
    for run in runs:
        process = next(p for p in processes if p["mode"] == run["mode"])
        if run["configuration"] != process["configuration"] or len(run["groups"]) != 2:
            raise ValueError("native configuration/group binding differs")
        groups = {group["kind"]: group for group in run["groups"]}
        if set(groups) != {"primary", "sources"}:
            raise ValueError("complete native contract groups required")
        nodes_by_mode[run["mode"]] = _contract_group(
            groups["primary"], run["mode"] == "candidate", primary, build, fixtures
        ) + _contract_group(
            groups["sources"], run["mode"] == "candidate", source, build, fixtures
        )
        for group in run["groups"]:
            launch = _signed(
                load_reference(group["native_launch"]),
                "R6_SWITCH_LAUNCH_ATTESTATION_KEY",
            )
            if (
                launch["kind"] != "r6.c10.native-process.v1"
                or launch["mode"] != run["mode"]
                or launch["group"] != group["kind"]
                or launch["build"] != _digest(build)
                or launch["configuration"] != run["configuration"]
                or launch["executable"] != build["executable"]
                or launch["operator"] != group["operator"]
                or launch["bootstrap"] != group["bootstrap"]
                or launch["generation_enabled"] is not (run["mode"] == "candidate")
                or launch["executable_digest"] != build["executable_digest"]
                or launch["target"]
                != load_reference(process["authority"])["record"]["target"]
                or not re.fullmatch("[0-9a-f]{64}", launch["command_digest"])
            ):
                raise ValueError(
                    "actual native process/configuration/bootstrap identity differs"
                )
    probe = contracts["source_probe"]
    record = _signed(load_reference(probe["registration"]), "R6_SWITCH_AUTHORITY_KEY")
    launch = _signed(
        load_reference(probe["launch"]), "R6_SWITCH_LAUNCH_ATTESTATION_KEY"
    )
    original_registry = _signed(
        load_reference(record["original_registry"]), "R6_SWITCH_AUTHORITY_KEY"
    )
    if record["target"] != original_registry["target"] or record["files"] != [
        "tests/services/agent_runtime/test_r6_d4_delivery.py"
    ]:
        raise ValueError(
            "source probe owner/schema/scenario differs from original authority"
        )
    config = load_reference(record["configuration"])
    base = load_reference(record["base_compatible_configuration"])
    if (
        config != dict(base, R6_GENERATION_ENABLED="true")
        or base.get("R6_GENERATION_ENABLED") != "false"
    ):
        raise ValueError("source probe may change only the generation configuration")
    if (
        record["kind"] != "r6.c10.local-source-probe.v1"
        or record["provider"] != "LOCAL_CONTROLLED_RECEIVER"
        or record["production_authorized"] is not False
    ):
        raise ValueError("separate controlled source probe registration required")
    if (
        record["operator"] != probe["operator"]
        or record["bootstrap"] != probe["bootstrap"]
        or record["base_compatible_configuration"]
        != next(p for p in processes if p["mode"] == "compatible")["configuration"]
    ):
        raise ValueError("source probe operator/bootstrap/base configuration differs")
    if (
        record["frozen_build"] != contracts["frozen_build"]
        or launch["build"] != _digest(build)
        or launch["configuration"] != record["configuration"]
        or launch["executable"] != build["executable"]
        or launch["executable_digest"] != build["executable_digest"]
        or launch["role"] != "native_source_probe"
        or launch["owner"] != record["target"]["owner"]
    ):
        raise ValueError("source probe safety-core/configuration changed")
    exit_receipt = load_reference(probe["process_exit"])
    if exit_receipt["processes"] != [dict(pid=launch["pid"], exit=0)]:
        raise ValueError("source probe actual process did not drain successfully")
    probe_nodes = _contract_group(
        probe,
        True,
        {"tests/services/agent_runtime/test_r6_d4_delivery.py"},
        build,
        fixtures,
    )
    if contracts["coverage"] != coverage_rows(nodes_by_mode, probe_nodes):
        raise ValueError("missing, changed, or unknown semantic coverage rows")
    return contracts


def coverage_specs():
    """Required semantic rows; each prefix must be executed, not merely named."""

    def nodes(file, *names):
        return ["tests/capa/" + file + ".py::" + name for name in names]

    return {
        "ROOT_FULL_UNION": nodes(
            "test_r6_d4_material",
            "test_complete_union_survives_manual_clear_and_live_revocation",
        ),
        "METADATA_BEFORE_BODY": nodes(
            "test_d4_source_access",
            "test_hidden_source_has_fixed_error_and_no_node_reads",
            "test_capa_edit_no_fmea_view_indistinguishable_zero_node_reads",
        ),
        "VERIFICATION_KNOWN_ORIGINS": nodes(
            "test_r6_sources_view",
            "test_clearing_verification_ref_cannot_erase_original_source_restriction",
            "test_retained_verification_sources_guard_all_body_consumers_and_review_references",
        ),
        "D5_SELECTED_CURRENT_HISTORY": nodes(
            "test_r6_d5_corrections",
            "test_hidden_other_measure_changes_stale_form_but_does_not_hide_readable_measure",
            "test_current_material_uses_correction_revision_identity",
        ),
        "LOCAL_SOURCE_GUARDS": nodes(
            "test_r6_local_closure",
            "test_normal_body_reads_require_new_current_verification_source_not_only_retained_sources",
            "test_d5_only_restrictions_choose_local_path_without_root_or_v_origins",
        ),
        "MANUAL_DOCUMENT_CANDIDATES": nodes(
            "test_r6_manual_doc_gate",
            "test_manual_candidate_and_live_input_changes_block_decision",
            "test_manual_decision_and_gate_freshness_do_not_reload_candidate_bodies",
        ),
        "KNOWN_LEGACY_CAPTURE": nodes(
            "test_r6_legacy_capture",
            "test_new_known_legacy_sources_survive_adoption_and_manual_replacement",
        )
        + nodes(
            "test_r6_sources_view",
            "test_clearing_verification_ref_cannot_erase_original_source_restriction",
        ),
        "CAPA24_PARENT_INCARNATION": nodes(
            "test_r6_legacy_capture",
            "test_capa_source_delete_recreate_does_not_rewrite_or_reauthorize_local_history",
            "test_capa_parent_edit_invalidates_old_manual_form_without_erasing_history",
        ),
        "MODEL_FIRST_CACHE_INFLIGHT": nodes(
            "test_r6_draft_release",
            "test_no_legacy_model_call_for_controlled_root_at_legal_stage",
            "test_same_body_becoming_controlled_invalidates_every_draft_release",
            "test_initiator_and_same_request_waiter_recheck_current_actor",
            "test_cache_is_bound_to_actual_recipient_not_only_model_name",
            "test_fmea_revoke_during_final_audit_still_blocks_response",
        ),
        "EMBEDDING": nodes(
            "test_r6_d4_consumers",
            "test_embedding_fetch_excludes_entire_controlled_report",
            "test_embedding_inflight_result_does_not_recreate_controlled_copy",
        ),
        "PPT_AND_REVIEW": nodes(
            "test_r6_sources_view",
            "test_cached_ppt_review_report_guard_precedes_json_select",
            "test_local_ppt_export_rechecks_verification_sources_after_commit",
        ),
        "C6_CONCURRENT_REPLAY": nodes(
            "test_r6_d5_corrections",
            "test_correction_preserves_adoption_and_exact_retry",
            "test_two_independent_http_transactions_only_one_correction",
            "test_lock_wait_rechecks_revoked_current_authority",
        ),
        "C6_STALE_APPROVAL_HISTORY": nodes(
            "test_r6_d5_correction_review",
            "test_normal_reject_then_correct_invalidates_old_expectation",
            "test_stored_model_round_requires_manual_reentry_before_approval",
        ),
        "MANUAL_STALE_REENTRY": nodes(
            "test_r6_manual_doc_gate",
            "test_normal_rejection_correction_and_manual_reentry_rejects_old_screen",
        ),
        "V1_V2_HISTORY": nodes(
            "test_r6_d5_correction_review",
            "test_v1_signature_bytes_remain_unchanged",
            "test_corrected_material_needs_explicit_v2_contract",
        ),
    }


def coverage_rows(nodes_by_mode, probe_nodes):
    rows = []
    for mode, nodes in nodes_by_mode.items():
        for tag, prefixes in coverage_specs().items():
            selected = []
            for prefix in prefixes:
                matching = [
                    node
                    for node in nodes
                    if node == prefix or node.startswith(prefix + "[")
                ]
                if not matching:
                    raise ValueError("missing executed semantic row: " + tag)
                selected.extend(matching)
            rows.append(
                dict(
                    tag=tag,
                    kind="NATIVE_INTERNAL_STORED_HISTORY"
                    if tag == "C6_STALE_APPROVAL_HISTORY"
                    else "NATIVE_INTERNAL_CONTRACT",
                    mode=mode,
                    nodeids=selected,
                )
            )
    prefixes = [
        "test_supported_report_inputs_and_single_external_source_deliver",
        "test_extra_external_origin_never_leaves_server",
        "test_old_local_text_contract_cannot_deliver_inherited_report_inputs",
        "test_model_result_rechecks_actor_after_transport_close",
    ]
    selected = []
    for name in prefixes:
        prefix = "tests/services/agent_runtime/test_r6_d4_delivery.py::" + name
        matching = [
            node
            for node in probe_nodes
            if node == prefix or node.startswith(prefix + "[")
        ]
        if not matching:
            raise ValueError("missing inherited-source probe counterexample")
        selected.extend(matching)
    rows.append(
        dict(
            tag="D4_D5_FULL_INHERITED_DELIVERY",
            kind="NATIVE_ENABLED_SOURCE_PROBE",
            mode="source_probe",
            nodeids=selected,
        )
    )
    return rows


AUDIT_BASELINE_DOMAIN = b"openqms.r6.c10.pre-attempt-audit-baseline.v1\0"
CORE_KEYS = ("current", "history", "review", "local", "decision", "current_sources")


def gate_sources():
    root = Path(__file__).resolve().parents[1]
    return {
        str(root / name): reference(root / name)["sha256"]
        for name in (
            "scripts/r6-compat-check.py",
            "backend/tests/e2e/test_r6_rollback_compat.py",
            "backend/tests/ci/test_r6_release_manifest.py",
        )
    }


def require_same_database(before, after):
    if {k: v for k, v in before.items() if k != "audit"} != {
        k: v for k, v in after.items() if k != "audit"
    }:
        raise ValueError("original non-audit database history changed")


def audit_by_id(rows):
    result = {}
    for row in rows:
        if set(row) != {
            "action",
            "changed_fields",
            "correlation_id",
            "factory_id",
            "ip_address",
            "log_id",
            "new_values",
            "old_values",
            "operated_at",
            "operated_by",
            "record_id",
            "table_name",
            "tenant_schema",
            "user_agent",
        }:
            raise ValueError("unknown audit projection fields")
        identifier = row["log_id"]
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ValueError("audit row identifiers must be present and unique")
        if str(UUID(identifier)) != identifier:
            raise ValueError("canonical audit row identity required")
        result[identifier] = row
    return result


def audit_delta(before, after):
    old, new = audit_by_id(before), audit_by_id(after)
    if any(new.get(identifier) != row for identifier, row in old.items()):
        raise ValueError("original audit row changed or disappeared")
    return [row for identifier, row in new.items() if identifier not in old]


def safe_failed_draft(row, request, report_id):
    audit_by_id([row])
    if (
        any(
            row[key] is not None
            for key in (
                "correlation_id",
                "factory_id",
                "ip_address",
                "tenant_schema",
                "user_agent",
            )
        )
        or row["table_name"] != "capa_eightd"
        or not isinstance(row["operated_at"], str)
        or not isinstance(row["operated_by"], str)
        or not isinstance(row["record_id"], str)
    ):
        raise ValueError("unexpected audit metadata or payload type")
    operated_at = datetime.fromisoformat(row["operated_at"])
    if operated_at.tzinfo is None or operated_at.utcoffset() is None:
        raise ValueError("aware audit timestamp required")
    fields = row["changed_fields"]
    if (
        set(fields)
        != {
            "duration_ms",
            "error",
            "format",
            "model",
            "request_id",
            "status_code",
            "step",
            "success",
        }
        or row["action"] != "AI_DRAFT"
        or row["record_id"] != report_id
        or row["operated_by"] != request["actor_id"]
        or fields["request_id"] != request["request_id"]
        or fields["step"] != request["path"].split("/")[1]
        or fields["status_code"] != 410
        or fields["success"] is not False
        or fields["model"] != "unknown"
        or fields["error"] != "CAPA_ENTRY_RETIRED_REFRESH_REPORT"
        or fields["format"] != "paragraph"
        or type(fields["duration_ms"]) not in (int, float)
        or not (0 <= fields["duration_ms"] <= 600000)
        or not math.isfinite(fields["duration_ms"])
        or row["old_values"] is not None
        or row["new_values"] is not None
    ):
        raise ValueError("unbound or successful/model/business audit addition")


def require_draft_audit_transition(before, after, requests, report_id):
    if (
        len(requests) != 2
        or {r["path"] for r in requests} != {"draft/d4", "draft/d5"}
        or len({r["request_id"] for r in requests}) != 2
    ):
        raise ValueError("distinct D4/D5 request evidence required")
    expected = {r["request_id"]: r for r in requests}
    prior_requests = {
        (row.get("changed_fields") or {}).get("request_id") for row in before
    }
    if set(expected) & prior_requests:
        raise ValueError("attempt request reuses historical audit identity")
    delta = audit_delta(before, after)
    observed = [(row.get("changed_fields") or {}).get("request_id") for row in delta]
    if len(delta) != 2 or len(set(observed)) != 2 or set(observed) != set(expected):
        raise ValueError(
            "audit delta must bijectively match both observed draft requests"
        )
    for row in delta:
        safe_failed_draft(row, expected[row["changed_fields"]["request_id"]], report_id)


def validate_pre_attempt(value, original_ref, target, current_snapshot=None):
    signed = load_reference(value)
    record = signed["record"]
    key = os.environ.get("R6_SWITCH_AUTHORITY_KEY", "")
    signature = hmac.new(
        key.encode(), AUDIT_BASELINE_DOMAIN + _digest(record).encode(), hashlib.sha256
    ).hexdigest()
    if (
        not key
        or not hmac.compare_digest(signed["signature"], signature)
        or record["kind"] != "r6.c10.pre-attempt-audit-baseline.v1"
        or record["original_snapshot"] != original_ref
        or record["target"] != target
        or record["gate_sources"] != gate_sources()
    ):
        raise ValueError(
            "independently authenticated exact pre-attempt baseline required"
        )
    original = load_reference(original_ref)
    baseline = load_reference(record["snapshot"])
    review = load_reference(record["historical_review"])
    proposed = load_reference(review["proposed_pre_run_snapshot"])
    if (
        review["kind"] != "r6.c10.historical-audit-review.v1"
        or review["original_snapshot"] != original_ref
        or any(original[k] != baseline[k] for k in CORE_KEYS)
    ):
        raise ValueError("historical baseline original C9 binding differs")
    require_same_database(original["database"], baseline["database"])
    require_same_database(proposed["database"], baseline["database"])
    if audit_by_id(proposed["database"]["audit"]) != audit_by_id(
        baseline["database"]["audit"]
    ):
        raise ValueError("baseline differs from independently reviewed exact history")
    delta = audit_delta(original["database"]["audit"], baseline["database"]["audit"])
    allowed = {row["log_id"]: row for row in review["historical_failure_rows"]}
    if (
        len(allowed) != len(review["historical_failure_rows"])
        or set(allowed) != {row["log_id"] for row in delta}
        or len({row["request_id"] for row in allowed.values()}) != len(allowed)
    ):
        raise ValueError("unknown or duplicated historical audit additions")
    for row in delta:
        approved = allowed[row["log_id"]]
        if _digest(row) != approved["row_sha256"]:
            raise ValueError("historical audit row differs from exact reviewed bytes")
        safe_failed_draft(
            row,
            dict(
                actor_id=approved["actor_id"],
                request_id=approved["request_id"],
                path="draft/" + approved["step"],
            ),
            original["report_id"],
        )
    if current_snapshot is not None:
        require_same_database(baseline["database"], current_snapshot["database"])
        if audit_by_id(baseline["database"]["audit"]) != audit_by_id(
            current_snapshot["database"]["audit"]
        ) or any(baseline[k] != current_snapshot[k] for k in CORE_KEYS):
            raise ValueError(
                "live pre-attempt state differs from frozen authenticated baseline"
            )
    return baseline


def validate_generation_off_probe(value, processes):
    result = _signed(load_reference(value), "R6_SWITCH_AUTHORITY_KEY")
    registration = _signed(
        load_reference(result["registration"]), "R6_SWITCH_AUTHORITY_KEY"
    )
    if (
        result["kind"] != "r6.c10.local-generation-off-result.v1"
        or registration["kind"] != "r6.c10.local-generation-off-probe.v1"
        or registration["production_authorized"] is not False
        or registration["provider"] != "LOCAL_CONTROLLED_RECEIVER"
        or registration["model_kind"] != "local"
        or registration["legitimate_pilot_and_model_approval"] is not True
        or registration["profile"] != "model_d5_proposal_r6_v1"
    ):
        raise ValueError(
            "separately registered legitimate local generation-off probe required"
        )
    authority = _signed(
        load_reference(registration["original_authority"]), "R6_SWITCH_AUTHORITY_KEY"
    )
    build = load_reference(registration["core_build"])
    if (
        _digest(build) != processes[1]["build"]
        or registration["schema_heads"] != build["schema_heads"]
    ):
        raise ValueError("local generation-off probe core/schema differs")
    if (
        authority["target"]
        != load_reference(processes[1]["authority"])["record"]["target"]
    ):
        raise ValueError("local generation-off probe owner differs")
    base = load_reference(registration["base_compatible_configuration"])
    configuration = load_reference(registration["configuration"])
    if (
        registration["base_compatible_configuration"] != processes[1]["configuration"]
        or configuration
        != dict(base, AGENT_R5_CONTROLLED_POLICY_FILE=registration["policy"]["path"])
        or configuration.get("R6_GENERATION_ENABLED") != "false"
    ):
        raise ValueError("local generation-off probe configuration differs")
    policy = load_reference(registration["policy"])
    if (
        policy["profile"] != registration["profile"]
        or policy["tenant_id"] != registration["tenant_id"]
        or policy["tenant_generation"] != registration["generation"]
        or policy["installation_id"] != registration["installation_id"]
    ):
        raise ValueError("local generation-off recognized policy identity differs")
    model = load_reference(registration["model_approval"])
    fingerprint = dict(
        approval={
            name: policy[name]
            for name in (
                "artifact",
                "artifact_sha256",
                "interpreter",
                "interpreter_sha256",
                "launcher_sha256",
            )
        },
        tenant_id=policy["tenant_id"],
        tenant_generation=policy["tenant_generation"],
        installation_id=policy["installation_id"],
        credential_epoch=policy["credential_epoch"],
        plugin_version=policy["plugin_version"],
        platform_port=policy["platform_port"],
        expires_at=str(datetime.fromisoformat(policy["expires_at"])),
        profile=policy["profile"],
    )
    pins = dict(
        policy_sha256=_digest(fingerprint),
        artifact_sha256=policy["artifact_sha256"],
        interpreter_sha256=policy["interpreter_sha256"],
        launcher_sha256=policy["launcher_sha256"],
        profile=policy["profile"],
    )
    fields = (
        "deployment_id",
        "name",
        "version",
        "tenant_generation",
        "kind",
        "provider",
        "model",
        "base_url",
        "allowed_addresses",
        "credential_ref",
        "executor_pins",
        "created_by",
    )
    data = {field: model[field] for field in fields}
    data["tenant_id"] = registration["tenant_id"]
    if model["api_protocol"] == "responses":
        data["api_protocol"] = "responses"
    model_signature = hmac.new(
        configuration["SECRET_KEY"].encode(),
        b"openqms.r5.model-deployment.v1\n"
        + json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    endpoint = urlsplit(model["base_url"])
    if (
        model["deployment_id"] != registration["model_deployment_id"]
        or model["kind"] != "local"
        or model["enabled"] is not True
        or model["tenant_generation"] != registration["generation"]
        or model["executor_pins"] != pins
        or not hmac.compare_digest(model["config_hmac"], model_signature)
        or endpoint.scheme != "http"
        or not endpoint.hostname
        or not ipaddress.ip_address(endpoint.hostname).is_loopback
        or not all(
            ipaddress.ip_address(address).is_loopback
            for address in model["allowed_addresses"]
        )
    ):
        raise ValueError(
            "legitimate immutable local model/policy approval provenance differs"
        )
    launch = load_reference(registration["launch"])
    signature = launch.pop("signature")
    key = os.environ.get("R6_SWITCH_LAUNCH_ATTESTATION_KEY", "")
    if (
        not key
        or not hmac.compare_digest(
            signature,
            hmac.new(
                key.encode(), _digest(launch).encode(), hashlib.sha256
            ).hexdigest(),
        )
        or launch["generation_enabled"] is not False
        or launch["build"] != _digest(build)
        or launch["configuration"] != registration["configuration"]
        or launch["executable"] != build["executable"]
        or launch["executable_digest"] != build["executable_digest"]
        or launch["role"] != "local_generation_off_probe"
    ):
        raise ValueError(
            "local generation-off actual PID/configuration identity differs"
        )
    if (
        load_reference(result["response"])
        != {"status": 503, "body": {"detail": "CAPA_NEW_GENERATION_DISABLED"}}
        or result["before"] != result["after"]
        or set(result["before"]) != {"tasks", "egress"}
        or result["new_provider_calls"] != 0
        or result["task_persistence_delta"] != 0
        or result["model_egress_delta"] != 0
        or result["app_exit"] not in {0, -15}
    ):
        raise ValueError(
            "local generation-off must reject exactly503 before task/provider writes"
        )
    verified_bytes(registration["operator"])
    return result


def validate_certificate(value):
    try:
        return _validate_certificate(value)
    except (
        KeyError,
        TypeError,
        AttributeError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            "missing, malformed, or unreadable compatibility evidence"
        ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    args = parser.parse_args()
    validate_certificate(json.loads(args.certificate.read_text()))
    print(
        json.dumps(
            {
                "status": "PASS",
                "production_authorized": False,
                "certificate": reference(args.certificate),
            }
        )
    )


if __name__ == "__main__":
    main()
