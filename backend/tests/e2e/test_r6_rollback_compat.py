"""Actual registered two-process, same-data compatibility rehearsal.

Requires the preserved owner-bound C9 directory and a fresh owner-only output
folder. No provider credential is loaded, no migrations or report phase writes.
"""

import asyncio
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

import pytest

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def editable_checks(exercise, original, mode):
    """Normal JWT writes on the separate genuine, still-editable control."""
    import httpx
    from tests.e2e.r6_exercise import write_private

    handoff = json.loads((original.parent / "task9-final-handoff.json").read_text())
    control_ref = handoff["task10_editable_control"]
    control_path = Path(control_ref["path"])
    assert hashlib.sha256(control_path.read_bytes()).hexdigest() == control_ref["sha256"]
    control = json.loads(control_path.read_text())
    session = json.loads(Path(control["credential_session_file"]).read_text())
    root = "/api/capa/" + control["report_id"]
    url = root + "/d5-measures/" + control["capa_d5_measures"][0]["measure_id"]
    async with httpx.AsyncClient(
        base_url=exercise.origin, trust_env=False, headers={"X-Tenant-ID": session["tenant"]}
    ) as client:
        login = await client.post(
            "/api/auth/login",
            json=dict(username=session["actors"]["colleague"]["username"], password=session["password"]),
        )
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        current = await client.get(root)
        assert current.status_code == 200 and current.json()["status"] == "D6_VERIFICATION"
        item = (await client.get(url)).json()
        assert item["adopted_text"] == control["capa_d5_measures"][0]["final_text"]
        proposals = await client.get(root + "/d5-proposals")
        assert proposals.status_code == 200
        assert {row["proposal_id"]: row["state"] for row in proposals.json()["items"]} == {
            row["proposal_id"]: row["state"] for row in control["capa_d5_proposals"]
        }
        body = dict(
            operation_key="c10-" + mode + "-" + uuid4().hex,
            expected_measure_version=item["current_version"],
            expected_material_version=item["material_version"],
            final_text=item["final_text"] + " [C10 " + mode + " correction]",
            reason="Synthetic compatibility correction",
        )
        other = dict(body, operation_key=body["operation_key"] + "-race", final_text=body["final_text"] + " other")
        results = await asyncio.gather(
            client.post(url + "/corrections", json=body), client.post(url + "/corrections", json=other)
        )
        assert sorted(r.status_code for r in results) == [200, 409]
        winner = 0 if results[0].status_code == 200 else 1
        accepted = [body, other][winner]
        replay = await client.post(url + "/corrections", json=accepted)
        assert replay.status_code == 200 and replay.json() == results[winner].json()
        fresh = (await client.get(url)).json()
        assert fresh["adopted_text"] == item["adopted_text"] and fresh["final_text"] == accepted["final_text"]
        assert (
            fresh["current_version"] != item["current_version"]
            and fresh["material_version"] != item["material_version"]
        )
        old_write = await client.put(root, json=dict(d5_correction="forbidden unversioned"))
        assert old_write.status_code in {409, 422}
        report = (await client.get(root)).json()
        manual_body = dict(
            d6_verification="Synthetic C10 " + mode + " manual verification retained",
            expected_entry_epoch=report["entry_epoch"],
            expected_material_version=report["material_version"],
        )
        manual = await client.put(root, json=manual_body)
        assert manual.status_code == 200
        stale = await client.post(url + "/corrections", json=dict(body, operation_key=uuid4().hex))
        assert stale.status_code == 409
        from app.core.tenant_transaction import TenantBinding
        from app.database import tenant_async_session
        from sqlalchemy import text

        binding = TenantBinding(UUID(control["tenant_id"]), control["schema"], control["generation"], "business")
        role = UUID(session["actors"]["colleague"]["role_id"])
        fresh = (await client.get(url)).json()
        revoke_body = dict(
            body,
            operation_key=uuid4().hex,
            expected_measure_version=fresh["current_version"],
            expected_material_version=fresh["material_version"],
        )
        async with tenant_async_session(binding=binding) as db:
            permission = await db.scalar(
                text("SELECT permission_level FROM role_permissions WHERE role_id=:id AND module='fmea'"), dict(id=role)
            )
            assert permission == 4
            await db.execute(
                text("UPDATE role_permissions SET permission_level=0 WHERE role_id=:id AND module='fmea'"),
                dict(id=role),
            )
            await db.commit()
        try:
            revoked = await client.post(url + "/corrections", json=revoke_body)
            assert revoked.status_code == 404
        finally:
            async with tenant_async_session(binding=binding) as db:
                await db.execute(
                    text("UPDATE role_permissions SET permission_level=:level WHERE role_id=:id AND module='fmea'"),
                    dict(id=role, level=permission),
                )
                await db.commit()
        history = await client.get(url + "/corrections")
        assert history.status_code == 200 and history.json()["corrections"]
        for original_revision in control["capa_d5_measure_revisions"]:
            keys = ("revision_id", "revision_no", "predecessor_id", "final_text", "reason", "actor_id")
            assert any(all(row[key] == original_revision[key] for key in keys) for row in history.json()["corrections"])
        return dict(
            mode=mode,
            concurrent_statuses=[r.status_code for r in results],
            retry_status=replay.status_code,
            unversioned_status=old_write.status_code,
            manual_status=manual.status_code,
            stale_status=stale.status_code,
            revoked_status=revoked.status_code,
            adopted_preserved=True,
            current_version=fresh["current_version"],
        )


async def revoked_reads(exercise, mode):
    """Owner changes only an existing view actor's source permission, restores it."""
    from sqlalchemy import text
    from app.database import tenant_async_session

    role = UUID(exercise.data["actors"]["view"]["role_id"])
    async with tenant_async_session(binding=exercise.binding()) as db:
        original = await db.scalar(
            text("SELECT permission_level FROM role_permissions WHERE role_id=:id AND module='fmea'"), dict(id=role)
        )
        assert original == 4
        await db.execute(
            text("UPDATE role_permissions SET permission_level=0 WHERE role_id=:id AND module='fmea'"), dict(id=role)
        )
        await db.commit()
    results = []
    try:
        snapshot = json.loads((exercise.output / "c9-evidence.json").read_text())
        measure = snapshot["measure_id"]
        for suffix in [
            "",
            "/d5-measures",
            "/d5-proposals",
            "/root-cause-verifications",
            "/local-closure",
            "/outcome-review",
            "/d5-measures/" + measure + "/corrections",
            "/sources/d5-proposal/" + snapshot["a"],
            "/sources/d5-proposal/" + snapshot["b"],
            "/sources/d5-measure/" + measure,
            "/ppt-exports/" + snapshot["existing_export"]["export_id"],
        ]:
            response = await exercise.clients["view"].get(exercise.root + suffix)
            if response.status_code == 200:
                value = response.json()
                assert suffix in {"/d5-measures", "/d5-proposals", "/root-cause-verifications"}
                assert value == [] or (
                    value.get("items") == []
                    and value.get("total") == 0
                    and value.get("legacy_text") in {None, snapshot["current"]["d5_correction"]}
                )
            else:
                assert response.status_code in {403, 404}, (suffix, response.status_code)
            results.append(dict(mode=mode, path=suffix, status=response.status_code, response=response.json()))
    finally:
        async with tenant_async_session(binding=exercise.binding()) as db:
            await db.execute(
                text("UPDATE role_permissions SET permission_level=:level WHERE role_id=:id AND module='fmea'"),
                dict(id=role, level=original),
            )
            await db.commit()
    return results


async def test_registered_compatible_process_preserves_same_corrected_report():
    context = {
        name: os.environ[name]
        for name in (
            "R6_C10_ORIGINAL",
            "R6_C10_OUTPUT",
            "R6_C10_INTERNAL_CONTRACTS",
            "R6_C10_AUDIT_BASELINE",
            "R6_C10_GENOFF_PROBE",
        )
    }
    context.update(
        {name: os.environ[name] for name in ("OPENQMS_GATE_HOOKS", "PYTEST_CURRENT_TEST") if name in os.environ}
    )
    original = Path(context["R6_C10_ORIGINAL"]).resolve()
    output = Path(os.environ["R6_C10_OUTPUT"]).resolve()
    assert output.is_dir() and output.stat().st_mode & 0o077 == 0
    assert not (output / "c10.json").exists(), "never overwrite an executed attempt"
    # The reviewed supplemental verifier imports the original frozen launch
    # classes. Its module-level environment is restored before either launch.
    runner_environment = dict(os.environ)
    runner_directory = Path.cwd()
    try:
        verifier = imported("c10_readonly_verifier", original / "continuation-v5/driver.py")
    finally:
        os.environ.clear()
        os.environ.update(runner_environment)
        os.chdir(runner_directory)
    os.environ.update(context)
    from app.database import tenant_async_session
    from app.services.capa_switch_evidence import authority, digest, validate_document, verify_inventory
    from tests.e2e.r6_exercise import write_private

    repo = Path(__file__).resolve().parents[3]
    checker = imported("c10_checker", repo / "scripts/r6-compat-check.py")
    env = json.loads((original / "environment.json").read_text())
    os.environ.update(env)
    compatible_env = json.loads((original / "environment.compat.json").read_text())
    assert compatible_env["R6_GENERATION_ENABLED"] == "false"
    assert {k: v for k, v in env.items() if k != "R6_GENERATION_ENABLED"} == {
        k: v for k, v in compatible_env.items() if k != "R6_GENERATION_ENABLED"
    }
    original_registry = json.loads((original / "authority.json").read_text())
    secrets = json.loads((original / "switch-environment.json").read_text())
    key, launch_key = secrets["R6_SWITCH_AUTHORITY_KEY"], secrets["R6_SWITCH_LAUNCH_ATTESTATION_KEY"]
    assert hmac.compare_digest(
        original_registry["signature"],
        hmac.new(key.encode(), digest(original_registry["record"]).encode(), hashlib.sha256).hexdigest(),
    )
    task_sources = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [
            Path(__file__).resolve(),
            repo / "scripts/r6-compat-check.py",
            repo / "backend/tests/ci/test_r6_release_manifest.py",
        ]
    }
    execution_status = "FAILED"
    processes = []
    control_checks = []
    source_checks = []
    try:
        for mode, environment in [("candidate", env), ("compatible", compatible_env)]:
            os.environ.update(environment)
            if "R6_GENERATION_ENABLED" not in environment:
                os.environ.pop("R6_GENERATION_ENABLED", None)
            os.environ.update(context)
            folder = output / mode
            folder.mkdir(mode=0o700)
            verifier.HERE = folder
            verifier.v4.HERE = folder
            async with verifier.ReadOnlyExercise() as exercise:
                exercise.output = folder
                exercise.environment = dict(environment)
                prepared = json.loads((original / "prepared.json").read_text())["d5"]
                exercise.port = prepared["policy"]["platform_port"]
                exercise.origin = f"http://127.0.0.1:{exercise.port}"
                await exercise.start(live=False, profile=prepared["profile"])
                observed = subprocess.check_output(
                    ["ps", "-p", str(exercise.server.pid), "-o", "lstart=", "-o", "command="], text=True
                ).strip()
                record = json.loads(json.dumps(original_registry["record"]))
                build_id = record["target"]["candidate_build" if mode == "candidate" else "compatible_build"]
                build = checker.load_reference(record["build_artifacts"][build_id])
                launch = dict(
                    pid=exercise.server.pid,
                    start=observed[:24],
                    command_digest=hashlib.sha256(observed.encode()).hexdigest(),
                    build=build_id,
                    role="server",
                    deployment_role=record["target"]["deployment_role"],
                    owner=record["target"]["owner"],
                    executable=build["executable"],
                    executable_digest=build["executable_digest"],
                    config_digest=build["config_digest"],
                )
                launch["signature"] = hmac.new(launch_key.encode(), digest(launch).encode(), hashlib.sha256).hexdigest()
                write_private(folder / "launch.json", launch)
                record["instances"] = [checker.reference(folder / "launch.json")]
                write_private(
                    folder / "authority.json",
                    dict(
                        record=record,
                        signature=hmac.new(key.encode(), digest(record).encode(), hashlib.sha256).hexdigest(),
                    ),
                )
                os.environ.update(
                    R6_SWITCH_AUTHORITY_FILE=str(folder / "authority.json"),
                    R6_SWITCH_AUTHORITY_KEY=key,
                    R6_SWITCH_LAUNCH_ATTESTATION_KEY=launch_key,
                )
                async with tenant_async_session(binding=exercise.binding()) as db:
                    target = await authority(db)
                    document = validate_document(json.loads((original / "exercise-renewed.json").read_text()), target)
                    await verify_inventory(db, document)
                old = json.loads((original / "build-and-switch.json").read_text())
                command = [
                    sys.executable,
                    "-B",
                    str(repo / "backend/scripts/r6-entry-switch.py"),
                    "status",
                    "--tenant",
                    exercise.data["tenant_id"],
                    "--actor",
                    exercise.data["actors"]["qe"]["user_id"],
                    "--operation",
                    old["operation"],
                    "--document",
                    str(original / "exercise-renewed.json"),
                ]
                process = await asyncio.create_subprocess_exec(
                    *command, env=dict(os.environ), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                assert process.returncode == 0, "registered status command failed"
                status = json.loads(stdout or stderr)
                assert (
                    status["state"] == "switched"
                    and status["epoch"] == 3
                    and status["operation_ref"] == old["operation"]
                )
                write_private(
                    folder / "registration.json",
                    dict(launch=launch, status=status, accepted_document_digest=document["document_digest"]),
                )
                await verifier.verify(exercise)
                if mode == "candidate":
                    handoff = json.loads((original.parent / "task9-final-handoff.json").read_text())
                    checker.validate_pre_attempt(
                        checker.reference(context["R6_C10_AUDIT_BASELINE"]),
                        handoff["receipts"]["c9-evidence.json"],
                        target,
                        json.loads((folder / "c9-evidence.json").read_text()),
                    )
                control_checks.append(await editable_checks(exercise, original, mode))
                source_checks.extend(await revoked_reads(exercise, mode))
                # No ordinary view-only actor may correct the terminal main.
                measure = exercise.root + "/d5-measures/" + verifier.MEASURE
                detail = await exercise.request("GET", measure)
                denied = await exercise.clients["view"].post(
                    measure + "/corrections",
                    json=dict(
                        operation_key=uuid4().hex,
                        expected_measure_version=detail["current_version"],
                        expected_material_version=detail["material_version"],
                        final_text="forbidden",
                        reason="terminal",
                    ),
                )
                assert denied.status_code in {403, 409}
                for path, method, body in [
                    ("d4-fmea-recommendations", "GET", None),
                    ("d5-fmea-recommendations", "GET", None),
                    ("draft/d4", "POST", dict(request_id=str(uuid4()), format="paragraph")),
                    ("draft/d5", "POST", dict(request_id=str(uuid4()), format="paragraph")),
                ]:
                    response = await exercise.clients["qe"].request(method, exercise.root + "/" + path, json=body)
                    assert response.status_code == 410
                    source_checks.append(
                        dict(
                            mode=mode,
                            path=path,
                            status=response.status_code,
                            request_id=body.get("request_id") if body else None,
                            actor_id=exercise.data["actors"]["qe"]["user_id"],
                            response=response.json(),
                        )
                    )
                qe_denied = await exercise.clients["qe"].post(
                    measure + "/corrections",
                    json=dict(
                        operation_key=uuid4().hex,
                        expected_measure_version=detail["current_version"],
                        expected_material_version=detail["material_version"],
                        final_text="terminal forbidden",
                        reason="terminal",
                    ),
                )
                assert qe_denied.status_code == 409 and qe_denied.json() == {"detail": "R6 material changed"}
                control_checks.append(
                    dict(
                        mode=mode,
                        terminal_correction_status=qe_denied.status_code,
                        view_correction_status=denied.status_code,
                    )
                )
                # Verify the final persisted state after every negative request.
                await verifier.verify(exercise)
                pid = exercise.server.pid
            processes.append(
                dict(
                    mode=mode,
                    pid=pid,
                    exit=exercise.server.returncode,
                    build=build_id,
                    generation_enabled=mode == "candidate",
                    configuration=checker.reference(
                        original / ("environment.json" if mode == "candidate" else "environment.compat.json")
                    ),
                    snapshot=checker.reference(folder / "c9-evidence.json"),
                    registration=checker.reference(folder / "registration.json"),
                    authority=checker.reference(folder / "authority.json"),
                )
            )
        write_private(
            output / "c10.json",
            dict(
                status="SCENARIO_ASSERTIONS_PASSED",
                report_id=verifier.REPORT,
                processes=processes,
                source_checks=source_checks,
                control_checks=control_checks,
                new_main_model_calls=0,
                paid_provider_calls=0,
                provider_credential_loaded=False,
            ),
        )
        handoff = json.loads((original.parent / "task9-final-handoff.json").read_text())
        certificate = dict(
            kind="r6.compatibility-rehearsal.v1",
            status="PASS",
            production_authorized=False,
            c9_snapshot=handoff["receipts"]["c9-evidence.json"],
            c9_readonly_manifest=handoff["receipts"]["manifest.json"],
            internal_contracts=checker.reference(context["R6_C10_INTERNAL_CONTRACTS"]),
            audit_baseline=checker.reference(context["R6_C10_AUDIT_BASELINE"]),
            generation_off_probe=checker.reference(context["R6_C10_GENOFF_PROBE"]),
            c9=handoff["receipts"]["composed-c9-evidence.json"],
            original_failed_receipt=handoff["original_failed_receipt"],
            c10=checker.reference(output / "c10.json"),
        )
        checker.validate_certificate(certificate)
        write_private(output / "certificate.json", certificate)
        execution_status = "PASS"
    finally:
        os.environ.update(context)
        assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == value for path, value in task_sources.items())
        write_private(
            output / "execution-receipt.json",
            dict(
                status=execution_status,
                task_sources=task_sources,
                processes=processes,
                new_model_calls=0,
                provider_credential_loaded=False,
                error_type=None if sys.exc_info()[0] is None else sys.exc_info()[0].__name__,
            ),
        )
        from app import database

        disposed = set()
        for engine in [tenant_async_session.kw.get("bind"), database.engine]:
            if engine is not None and id(engine) not in disposed:
                await engine.dispose()
                disposed.add(id(engine))


@pytest.mark.parametrize(
    "change",
    [
        "production",
        "missing_c9",
        "missing_c10",
        "missing_sources",
        "missing_history",
        "single_process",
        "undrained",
        "main_or_r5",
        "source_500",
        "missing_contracts",
        "missing_correction",
        "changed_approved_snapshot",
        "unknown_instance",
        "unexpected_shared_model_audit",
        "unexpected_shared_successful_draft",
        "duplicate_draft_request_audits",
        "changed_original_database_proposal",
        "failed_audit_extra_payload",
        "failed_audit_metadata_payload",
        "failed_audit_unknown_row_field",
    ],
)
async def test_executed_certificate_rejects_incomplete_compatibility(change, tmp_path):
    """Fault injection keeps valid content hashes; failures must be semantic."""
    repo = Path(__file__).resolve().parents[3]
    checker = imported("c10_negative_checker", repo / "scripts/r6-compat-check.py")
    output = Path(os.environ["R6_C10_OUTPUT"])
    certificate = json.loads((output / "certificate.json").read_text())
    checker.validate_certificate(certificate)  # Positive control on the exact executed artifacts.

    def replaced(reference, mutate, name):
        value = checker.load_reference(reference)
        mutate(value)
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return checker.reference(path)

    if change == "production":
        certificate["production_authorized"] = True
    elif change in {"missing_c9", "missing_c10"}:
        certificate.pop(change.removeprefix("missing_"))
    elif change == "missing_contracts":
        certificate.pop("internal_contracts")
    else:

        def altered(c10):
            if change in {
                "failed_audit_extra_payload",
                "failed_audit_metadata_payload",
                "failed_audit_unknown_row_field",
            }:
                request = next(c for c in c10["source_checks"] if c["mode"] == "compatible" and c["path"] == "draft/d4")

                def payload(snapshot):
                    row = next(
                        row
                        for row in snapshot["database"]["audit"]
                        if (row.get("changed_fields") or {}).get("request_id") == request["request_id"]
                    )
                    if change == "failed_audit_extra_payload":
                        row["changed_fields"]["business_payload"] = "synthetic forbidden"
                    elif change == "failed_audit_metadata_payload":
                        row["user_agent"] = {"business_payload": "synthetic forbidden"}
                    else:
                        row["prompt"] = "synthetic forbidden"

                c10["processes"][1]["snapshot"] = replaced(c10["processes"][1]["snapshot"], payload, "payload.json")
                return
            if change in {
                "unexpected_shared_model_audit",
                "unexpected_shared_successful_draft",
                "changed_original_database_proposal",
                "failed_audit_extra_payload",
                "failed_audit_metadata_payload",
                "failed_audit_unknown_row_field",
            }:
                forged_id = str(uuid4())
                audit_template = checker.load_reference(c10["processes"][0]["snapshot"])["database"]["audit"][-1]

                def shared(snapshot):
                    if change == "changed_original_database_proposal":
                        snapshot["database"]["capa_d5_proposals"][0]["body"]["original_text"] += " synthetic tamper"
                    else:
                        row = json.loads(json.dumps(audit_template))
                        row["log_id"] = forged_id
                        if change == "unexpected_shared_model_audit":
                            row["action"] = "MODEL_EGRESS_COMPLETED"
                            row["changed_fields"] = {"synthetic_negative_fixture": True}
                        else:
                            row["action"] = "AI_DRAFT"
                            row["changed_fields"].update(success=True, status_code=200)
                        snapshot["database"]["audit"].append(row)

                for index, process in enumerate(c10["processes"]):
                    process["snapshot"] = replaced(process["snapshot"], shared, "shared-" + str(index) + ".json")
                return
            if change == "duplicate_draft_request_audits":
                before = checker.load_reference(c10["processes"][0]["snapshot"])["database"]["audit"]
                request = next(c for c in c10["source_checks"] if c["mode"] == "compatible" and c["path"] == "draft/d4")

                def duplicated(snapshot):
                    row = next(
                        row
                        for row in snapshot["database"]["audit"]
                        if (row.get("changed_fields") or {}).get("request_id") == request["request_id"]
                    )
                    duplicate = json.loads(json.dumps(row))
                    duplicate["log_id"] = str(uuid4())
                    snapshot["database"]["audit"] = before + [row, duplicate]

                c10["processes"][1]["snapshot"] = replaced(
                    c10["processes"][1]["snapshot"], duplicated, "duplicate.json"
                )
                return
            if change == "single_process":
                c10["processes"] = c10["processes"][:1]
            elif change == "undrained":
                c10["processes"][0]["exit"] = None
            elif change == "main_or_r5":
                c10["processes"][1]["build"] = hashlib.sha256(b"synthetic-unregistered-main-or-R5-artifact").hexdigest()
            elif change == "source_500":
                c10["source_checks"][0]["status"] = 500
            elif change == "missing_correction":
                c10["control_checks"] = []
            elif change in {"missing_sources", "missing_history", "changed_approved_snapshot"}:
                key = {
                    "missing_sources": "current_sources",
                    "missing_history": "history",
                    "changed_approved_snapshot": "review",
                }[change]
                c10["processes"][1]["snapshot"] = replaced(
                    c10["processes"][1]["snapshot"], lambda s: s.__setitem__(key, {}), "snapshot.json"
                )
            elif change == "unknown_instance":

                def unknown(registry):
                    registry["record"]["instances"].append(dict(path="/unknown/unowned-process", sha256="0" * 64))
                    # Valid owner signature cannot excuse an unknown instance.
                    registry["signature"] = hmac.new(
                        os.environ["R6_SWITCH_AUTHORITY_KEY"].encode(),
                        checker._digest(registry["record"]).encode(),
                        hashlib.sha256,
                    ).hexdigest()

                c10["processes"][1]["authority"] = replaced(c10["processes"][1]["authority"], unknown, "authority.json")

        certificate["c10"] = replaced(certificate["c10"], altered, "c10.json")
    with pytest.raises(ValueError):
        checker.validate_certificate(certificate)
