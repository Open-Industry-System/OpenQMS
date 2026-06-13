import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.services.embedding_outbox import enqueue_embedding
from app.services.product_line_service import validate_product_line
from app.state_machines.eightd_state import EightDState, can_transition

EMBEDDING_FIELDS = {"d2_description", "d4_root_cause", "d5_correction", "d7_prevention"}


async def list_capas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line: str | None = None,
    overdue: bool = False,
    pending_action: bool = False,
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[CAPAEightD], int]:
    from datetime import datetime
    now = datetime.now(UTC)

    query = select(CAPAEightD)
    count_query = select(func.count(CAPAEightD.report_id))

    if status:
        query = query.where(CAPAEightD.status == status)
        count_query = count_query.where(CAPAEightD.status == status)

    if product_line:
        query = query.where(CAPAEightD.product_line_code == product_line)
        count_query = count_query.where(CAPAEightD.product_line_code == product_line)

    if allowed_product_line_codes is not None:
        query = query.where(CAPAEightD.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(CAPAEightD.product_line_code.in_(allowed_product_line_codes))

    if factory_id is not None:
        query = query.where(CAPAEightD.factory_id == factory_id)
        count_query = count_query.where(CAPAEightD.factory_id == factory_id)

    if overdue:
        query = query.where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )
        count_query = count_query.where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )

    if pending_action:
        query = query.where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
        )
        count_query = count_query.where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
        )

    query = query.order_by(CAPAEightD.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_capa(db: AsyncSession, report_id: uuid.UUID) -> CAPAEightD | None:
    result = await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == report_id))
    return result.scalar_one_or_none()


async def create_capa(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
    factory_id: uuid.UUID | None = None,
) -> CAPAEightD:
    await validate_product_line(db, product_line_code)
    # Check if duplicate document_no exists
    existing_result = await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == document_no)
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    report_id = uuid.uuid4()
    capa = CAPAEightD(
        report_id=report_id,
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        product_line_code=product_line_code,
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(capa)

    # Audit log
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=report_id,
        action="CREATE",
        changed_fields={
            "title": title,
            "document_no": document_no,
            "severity": severity,
            "due_date": str(due_date) if due_date else None,
            "product_line_code": product_line_code,
            "status": capa.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    await db.refresh(capa)
    return capa


async def _create_capa_without_commit(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
    factory_id: uuid.UUID | None = None,
) -> CAPAEightD:
    """Create CAPA without committing — caller must commit."""
    await validate_product_line(db, product_line_code)
    # Check if duplicate document_no exists
    existing_result = await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == document_no)
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    report_id = uuid.uuid4()
    capa = CAPAEightD(
        report_id=report_id,
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        product_line_code=product_line_code,
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(capa)

    # Audit log
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=report_id,
        action="CREATE",
        changed_fields={
            "title": title,
            "document_no": document_no,
            "severity": severity,
            "due_date": str(due_date) if due_date else None,
            "product_line_code": product_line_code,
            "status": capa.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.flush()
    except IntegrityError:
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    await db.refresh(capa)
    return capa


async def update_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    update_data: dict,
    user_id: uuid.UUID,
) -> CAPAEightD:
    if "product_line_code" in update_data and update_data["product_line_code"] is not None:
        await validate_product_line(db, update_data["product_line_code"])

    # Detect embedding field changes BEFORE mutating capa
    embedding_changed = {
        k for k, v in update_data.items()
        if k in EMBEDDING_FIELDS and getattr(capa, k) != v
    }

    changed_fields = {}
    for key, value in update_data.items():
        if value is not None and hasattr(capa, key):
            old_value = getattr(capa, key)
            if old_value != value:
                if isinstance(value, (uuid.UUID, date, datetime)):
                    changed_fields[key] = str(value)
                else:
                    changed_fields[key] = value
                setattr(capa, key, value)

    if changed_fields:
        audit_log = AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="UPDATE",
            changed_fields=changed_fields,
            operated_by=user_id,
        )
        db.add(audit_log)

    # Close linked risk alerts if CAPA reached D8_CLOSURE
    if capa.status == "D8_CLOSURE":
        from sqlalchemy import update

        from app.models.supplier_risk import SupplierRiskAlert
        await db.execute(
            update(SupplierRiskAlert)
            .where(SupplierRiskAlert.linked_capa_id == capa.report_id)
            .where(SupplierRiskAlert.status != "closed")
            .values(status="closed", handled_at=func.now())
        )

    if embedding_changed:
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    await db.commit()
    await db.refresh(capa)
    return capa


async def advance_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    user_id: uuid.UUID,
    d7_skip_reasons: list[dict] | None = None,
) -> CAPAEightD:
    current = EightDState(capa.status)
    transitions = [
        EightDState.D1_TEAM,
        EightDState.D2_DESCRIPTION,
        EightDState.D3_INTERIM,
        EightDState.D4_ROOT_CAUSE,
        EightDState.D5_CORRECTION,
        EightDState.D6_VERIFICATION,
        EightDState.D7_PREVENTION,
        EightDState.D8_CLOSURE,
        EightDState.ARCHIVED,
    ]

    if current in transitions:
        idx = transitions.index(current)
        next_state = transitions[idx + 1] if idx + 1 < len(transitions) else EightDState.ARCHIVED
    else:
        raise ValueError(f"Cannot advance from {capa.status}")

    if not can_transition(current, next_state):
        raise ValueError(f"Cannot transition from {capa.status} to {next_state.value}")

    old_status = capa.status
    capa.status = next_state.value

    # Audit log for transition
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="TRANSITION",
        changed_fields={
            "old_status": old_status,
            "new_status": next_state.value,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    # D7 skip reasons audit
    if d7_skip_reasons and old_status == "D7_PREVENTION":
        skip_log = AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="D7_SKIP_CONFIRMATION",
            changed_fields={"skipped_nodes": d7_skip_reasons},
            operated_by=user_id,
        )
        db.add(skip_log)

    # Write to MES outbox before commit
    if capa.product_line_code and old_status != capa.status:
        from sqlalchemy import select

        from app.models.mes import MESConnection
        from app.services.mes_service import MESPushService

        query = select(MESConnection).where(
            MESConnection.is_active == True,
            MESConnection.product_line_code == capa.product_line_code,
        )
        result = await db.execute(query)
        for conn in result.scalars().all():
            cfg = conn.config or {}
            if conn.connector_type != "mock" and not cfg.get("push_enabled", False):
                continue
            await MESPushService.push_event(
                db,
                event_type="capa_status_change",
                connection_id=conn.connection_id,
                factory_id=conn.factory_id,
                payload={
                    "capa_id": str(capa.report_id),
                    "old_status": old_status,
                    "new_status": capa.status,
                    "changed_at": datetime.now(UTC).isoformat(),
                    "product_line_code": capa.product_line_code,
                },
            )

    await db.commit()  # existing commit includes outbox
    await db.refresh(capa)
    return capa


async def link_fmea(
    db: AsyncSession,
    capa: CAPAEightD,
    fmea_ref_id: uuid.UUID,
    user_id: uuid.UUID,
    fmea_node_id: str | None = None,
) -> CAPAEightD:
    old_fmea_ref_id = capa.fmea_ref_id
    old_fmea_node_id = capa.fmea_node_id
    capa.fmea_ref_id = fmea_ref_id
    capa.fmea_node_id = fmea_node_id

    # Audit log
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="LINK_FMEA",
        changed_fields={
            "old_fmea_ref_id": str(old_fmea_ref_id) if old_fmea_ref_id else None,
            "new_fmea_ref_id": str(fmea_ref_id),
            "old_fmea_node_id": old_fmea_node_id,
            "new_fmea_node_id": fmea_node_id,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(capa)
    return capa


def get_d7_recommendations(
    capa_data: dict,
    fmea_docs: list[dict],
    allowed_product_lines: list[str] | None = None,
) -> list[dict]:
    """Compute D7 FMEA recommendations for a CAPA.

    Args:
        capa_data: dict with fmea_ref_id, fmea_node_id, d4_root_cause, d5_correction, product_line_code
        fmea_docs: list of dicts with fmea_id, document_no, graph_data (already filtered by product line)
        allowed_product_lines: user's accessible product line codes

    Returns:
        List of recommendation dicts matching D7Recommendation schema.
    """
    from app.utils.text import extract_keywords

    recommendations: list[dict] = []

    # Split into linked FMEA and other FMEAs
    linked_fmea_id = capa_data.get("fmea_ref_id")
    linked_fmea = None
    other_fmeas = []

    for doc in fmea_docs:
        if doc["fmea_id"] == linked_fmea_id:
            linked_fmea = doc
        else:
            other_fmeas.append(doc)

    # --- Linked matching ---
    if linked_fmea and linked_fmea.get("graph_data"):
        graph = linked_fmea["graph_data"]
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        # Build reverse index: target -> list of (source, edge_type)
        reverse_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

        # Build forward index: source -> list of (target, edge_type)
        forward_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

        target_node_id = capa_data.get("fmea_node_id")
        target_node = node_map.get(target_node_id) if target_node_id else None

        failure_mode_ids: list[str] = []

        if target_node:
            if target_node["type"] == "FailureCause":
                # Find parent FailureMode via CAUSE_OF forward (FailureCause -> FailureMode)
                for tgt, etype in forward_edges.get(target_node_id, []):
                    if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                        failure_mode_ids.append(tgt)
            elif target_node["type"] == "FailureMode":
                failure_mode_ids.append(target_node_id)
            else:
                # Function or other type: find FailureModes via HAS_FAILURE_MODE
                for tgt, etype in forward_edges.get(target_node_id, []):
                    if etype == "HAS_FAILURE_MODE" and node_map.get(tgt, {}).get("type") == "FailureMode":
                        failure_mode_ids.append(tgt)
        else:
            # No specific node: find FailureModes matching D4 keywords
            keywords = extract_keywords(capa_data.get("d4_root_cause", ""))
            for n in graph.get("nodes", []):
                if n.get("type") == "FailureMode":
                    name = n.get("name", "")
                    if any(kw in name or name in kw for kw in keywords):
                        failure_mode_ids.append(n["id"])

        # For each FailureMode, find FailureCauses and PreventionControls
        for fm_id in failure_mode_ids:
            fm_node = node_map.get(fm_id)
            if not fm_node:
                continue

            # Find FailureCauses via CAUSE_OF reverse (FailureCause --CAUSE_OF--> FailureMode)
            cause_ids = []
            for src, etype in reverse_edges.get(fm_id, []):
                if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause":
                    cause_ids.append(src)

            if not cause_ids:
                # No FailureCause -- skip (linked matching filters these out)
                continue

            for cause_id in cause_ids:
                cause_node = node_map.get(cause_id)
                # Find PreventionControl via PREVENTED_BY forward
                control_id = None
                control_name = None
                for tgt, etype in forward_edges.get(cause_id, []):
                    if etype == "PREVENTED_BY" and node_map.get(tgt, {}).get("type") == "PreventionControl":
                        control_id = tgt
                        control_name = node_map[tgt].get("name")
                        break

                recommendations.append({
                    "fmea_id": linked_fmea["fmea_id"],
                    "fmea_document_no": linked_fmea["document_no"],
                    "failure_mode_node_id": fm_id,
                    "failure_mode_name": fm_node.get("name", ""),
                    "failure_cause_node_id": cause_id,
                    "failure_cause_name": cause_node.get("name", "") if cause_node else None,
                    "prevention_control_node_id": control_id,
                    "prevention_control_name": control_name,
                    "match_source": "linked",
                    "match_reason": "关联FMEA失效模式",
                    "related_d4_keywords": extract_keywords(capa_data.get("d4_root_cause", "")),
                    "suggested_prevention": capa_data.get("d5_correction"),
                })

    # --- Keyword matching (other FMEAs) ---
    keywords = extract_keywords(capa_data.get("d4_root_cause", ""))
    if keywords and other_fmeas:
        seen_keys: set[str] = set()
        # Exclude already-added linked recommendations
        for r in recommendations:
            seen_keys.add(f"{r['fmea_id']}_{r['failure_mode_node_id']}")

        keyword_results: list[tuple[int, dict]] = []  # (match_count, rec)

        for doc in other_fmeas:
            # product_line filtering already done at query level
            graph = doc.get("graph_data")
            if not graph:
                continue

            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            reverse_edges_kw: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                reverse_edges_kw.setdefault(e["target"], []).append((e["source"], e["type"]))

            forward_edges_kw: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                forward_edges_kw.setdefault(e["source"], []).append((e["target"], e["type"]))

            # Pre-index FailureCause names+descriptions per FailureMode for broader keyword matching
            fm_cause_texts: dict[str, list[str]] = {}  # fm_id -> [cause_name, cause_desc, ...]
            for e in edges:
                if e["type"] == "CAUSE_OF":
                    cause_node = node_map.get(e["source"])
                    if cause_node and cause_node.get("type") == "FailureCause":
                        texts = [cause_node.get("name", "")]
                        if cause_node.get("description"):
                            texts.append(cause_node["description"])
                        fm_cause_texts.setdefault(e["target"], []).extend(texts)

            for n in graph.get("nodes", []):
                if n.get("type") != "FailureMode":
                    continue

                # Match against FailureMode name/description AND its FailureCause name/description
                all_text = [n.get("name", "")]
                if n.get("description"):
                    all_text.append(n["description"])
                all_text.extend(fm_cause_texts.get(n["id"], []))
                matched_kws = [kw for kw in keywords if any(kw in t or t in kw for t in all_text)]
                if not matched_kws:
                    continue

                # Find FailureCauses
                cause_ids = []
                for src, etype in reverse_edges_kw.get(n["id"], []):
                    if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause":
                        cause_ids.append(src)

                if not cause_ids:
                    # No FailureCause -- include with null cause/control, disable auto-fill
                    dedup_key = f"{doc['fmea_id']}_{n['id']}_none"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    keyword_results.append((len(matched_kws), {
                        "fmea_id": doc["fmea_id"],
                        "fmea_document_no": doc["document_no"],
                        "failure_mode_node_id": n["id"],
                        "failure_mode_name": n.get("name", ""),
                        "failure_cause_node_id": None,
                        "failure_cause_name": None,
                        "prevention_control_node_id": None,
                        "prevention_control_name": None,
                        "match_source": "keyword",
                        "match_reason": f"关键词匹配: {', '.join(matched_kws)}",
                        "related_d4_keywords": matched_kws,
                        "suggested_prevention": capa_data.get("d5_correction"),
                    }))
                    continue

                for cause_id in cause_ids:
                    dedup_key = f"{doc['fmea_id']}_{n['id']}_{cause_id}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    cause_node = node_map.get(cause_id)
                    control_id = None
                    control_name = None
                    for tgt, etype in forward_edges_kw.get(cause_id, []):
                        if etype == "PREVENTED_BY" and node_map.get(tgt, {}).get("type") == "PreventionControl":
                            control_id = tgt
                            control_name = node_map[tgt].get("name")
                            break

                    keyword_results.append((len(matched_kws), {
                        "fmea_id": doc["fmea_id"],
                        "fmea_document_no": doc["document_no"],
                        "failure_mode_node_id": n["id"],
                        "failure_mode_name": n.get("name", ""),
                        "failure_cause_node_id": cause_id,
                        "failure_cause_name": cause_node.get("name", "") if cause_node else None,
                        "prevention_control_node_id": control_id,
                        "prevention_control_name": control_name,
                        "match_source": "keyword",
                        "match_reason": f"关键词匹配: {', '.join(matched_kws)}",
                        "related_d4_keywords": matched_kws,
                        "suggested_prevention": capa_data.get("d5_correction"),
                    }))

        # Sort by match count descending, take top 5
        keyword_results.sort(key=lambda x: x[0], reverse=True)
        for _, rec in keyword_results[:5]:
            recommendations.append(rec)

    return recommendations


async def get_capas_by_fmea_node(
    db: AsyncSession, fmea_id: str, fmea_node_id: str | None = None
) -> list[dict]:
    q = select(CAPAEightD).where(CAPAEightD.fmea_ref_id == fmea_id)
    if fmea_node_id:
        q = q.where(CAPAEightD.fmea_node_id == fmea_node_id)
    result = await db.execute(q)
    return [
        {
            "report_id": str(c.report_id),
            "document_no": c.document_no,
            "title": c.title,
            "status": c.status,
            "product_line_code": c.product_line_code,
        }
        for c in result.scalars().all()
    ]
