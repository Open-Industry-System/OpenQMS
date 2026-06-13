import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.management_review import ManagementReview, ReviewOutput


def _parse_integrity_error(error: IntegrityError, operation: str) -> str:
    """将数据库完整性错误转换为中文友好提示"""
    msg = str(error.orig) if hasattr(error, "orig") else str(error)

    if "doc_no" in msg and "unique" in msg.lower():
        return "该年份下的评审编号已存在，请刷新后重试"
    if "chair_person_id" in msg and "foreign key" in msg.lower():
        return "主持人不存在或已被删除"
    if "product_line_code" in msg and "foreign key" in msg.lower():
        return "产品线不存在或已被删除"
    if "responsible_id" in msg and "foreign key" in msg.lower():
        return "责任人不存在或已被删除"
    if "verified_by" in msg and "foreign key" in msg.lower():
        return "验证人不存在或已被删除"
    if "review_id" in msg and "foreign key" in msg.lower():
        return "关联的评审记录不存在"

    return f"{operation}失败，数据冲突或约束违规"


async def _generate_doc_no(db: AsyncSession) -> str:
    year = datetime.now().year
    prefix = f"MR-{year}"
    result = await db.execute(
        select(func.count()).where(ManagementReview.doc_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _audit(
    db: AsyncSession,
    action: str,
    record_id: uuid.UUID,
    user_id: uuid.UUID,
    changed_fields: dict,
    *,
    table_name: str = "management_reviews",
) -> None:
    db.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields,
        operated_by=user_id,
    ))


async def list_reviews(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line_code: str | None = None,
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[ManagementReview], int]:
    query = select(ManagementReview)
    count_q = select(func.count()).select_from(ManagementReview)

    if status:
        query = query.where(ManagementReview.status == status)
        count_q = count_q.where(ManagementReview.status == status)
    if product_line_code:
        query = query.where(ManagementReview.product_line_code == product_line_code)
        count_q = count_q.where(ManagementReview.product_line_code == product_line_code)
    elif allowed_product_line_codes is not None:
        query = query.where(ManagementReview.product_line_code.in_(allowed_product_line_codes))
        count_q = count_q.where(ManagementReview.product_line_code.in_(allowed_product_line_codes))
    if factory_id is not None:
        query = query.where(ManagementReview.factory_id == factory_id)
        count_q = count_q.where(ManagementReview.factory_id == factory_id)

    query = query.order_by(ManagementReview.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    total = (await db.execute(count_q)).scalar() or 0
    return list(items), total


async def get_review(db: AsyncSession, review_id: uuid.UUID) -> ManagementReview | None:
    return await db.get(ManagementReview, review_id)


async def create_review(
    db: AsyncSession,
    *,
    title: str,
    review_date,
    product_line_code: str | None,
    location: str | None,
    chair_person_id: uuid.UUID,
    participants: list[dict] | None,
    user_id: uuid.UUID,
    factory_id: uuid.UUID | None = None,
) -> ManagementReview:
    doc_no = await _generate_doc_no(db)
    review = ManagementReview(
        doc_no=doc_no,
        title=title,
        review_date=review_date,
        product_line_code=product_line_code,
        location=location,
        chair_person_id=chair_person_id,
        participants=participants,
        status="draft",
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(review)
    await _audit(db, "CREATE", review.review_id, user_id, {
        "doc_no": doc_no, "title": title, "status": "draft",
    })
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(_parse_integrity_error(e, "创建评审"))
    await db.refresh(review)
    return review


async def update_review(
    db: AsyncSession,
    review: ManagementReview,
    *,
    user_id: uuid.UUID,
    **fields,
) -> ManagementReview:
    if review.status not in ("draft", "data_collected"):
        raise ValueError("only draft or data_collected reviews can be edited")

    changed = {}
    editable = [
        "title", "review_date", "actual_date", "product_line_code",
        "location", "chair_person_id", "participants",
        "meeting_minutes", "manual_inputs", "attachments",
    ]
    for f in editable:
        val = fields.get(f)
        if val is None:
            continue
        old = getattr(review, f)
        if val != old:
            changed[f] = {"before": old, "after": val}
            setattr(review, f, val)

    if not changed:
        return review

    review.updated_by = user_id
    await _audit(db, "UPDATE", review.review_id, user_id, changed)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(_parse_integrity_error(e, "更新评审"))
    await db.refresh(review)
    return review


async def delete_review(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> None:
    if review.status != "draft":
        raise ValueError("only draft reviews can be deleted")
    await _audit(db, "DELETE", review.review_id, user_id, {
        "doc_no": review.doc_no, "title": review.title,
    })
    try:
        await db.delete(review)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("cannot delete review")


async def collect_data(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> ManagementReview:
    if review.status != "draft":
        raise ValueError("only draft reviews can collect data")
    if not review.title or not review.review_date or not review.chair_person_id:
        raise ValueError("title, review_date, and chair_person_id are required")

    review.data_package = await _aggregate_data_package(db, review.product_line_code)
    review.status = "data_collected"
    review.updated_by = user_id
    await _audit(db, "TRANSITION", review.review_id, user_id, {
        "status": {"before": "draft", "after": "data_collected"},
    })
    await db.commit()
    await db.refresh(review)
    return review


async def refresh_data(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> ManagementReview:
    if review.status != "data_collected":
        raise ValueError("can only refresh data in data_collected status")

    review.data_package = await _aggregate_data_package(db, review.product_line_code)
    review.updated_by = user_id
    await _audit(db, "UPDATE", review.review_id, user_id, {"data_package": "refreshed"})
    await db.commit()
    await db.refresh(review)
    return review


async def back_to_draft(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> ManagementReview:
    if review.status != "data_collected":
        raise ValueError("can only go back to draft from data_collected")
    review.status = "draft"
    review.updated_by = user_id
    await _audit(db, "TRANSITION", review.review_id, user_id, {
        "status": {"before": "data_collected", "after": "draft"},
    })
    await db.commit()
    await db.refresh(review)
    return review


async def start_review(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> ManagementReview:
    if review.status != "data_collected":
        raise ValueError("can only start review from data_collected")
    review.status = "in_review"
    review.updated_by = user_id
    await _audit(db, "TRANSITION", review.review_id, user_id, {
        "status": {"before": "data_collected", "after": "in_review"},
    })
    await db.commit()
    await db.refresh(review)
    return review


async def close_review(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> ManagementReview:
    if review.status != "in_review":
        raise ValueError("can only close from in_review")
    has_outputs = (await db.execute(
        select(func.count()).select_from(ReviewOutput)
        .where(ReviewOutput.review_id == review.review_id)
    )).scalar() or 0
    if not review.meeting_minutes and has_outputs == 0:
        raise ValueError("must have at least 1 output or meeting_minutes before closing")

    review.status = "closed"
    review.actual_date = datetime.now(UTC).date()
    review.updated_by = user_id
    await _audit(db, "TRANSITION", review.review_id, user_id, {
        "status": {"before": "in_review", "after": "closed"},
    })
    await db.commit()
    await db.refresh(review)
    return review


async def reopen_review(
    db: AsyncSession, review: ManagementReview, user_id: uuid.UUID,
) -> ManagementReview:
    if review.status != "closed":
        raise ValueError("can only reopen from closed")
    review.status = "in_review"
    review.updated_by = user_id
    await _audit(db, "TRANSITION", review.review_id, user_id, {
        "status": {"before": "closed", "after": "in_review"},
    })
    await db.commit()
    await db.refresh(review)
    return review


async def _aggregate_data_package(
    db: AsyncSession, product_line_code: str | None,
) -> dict:
    from app.models.audit_finding import AuditFinding
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument
    from app.models.quality_goal import QualityGoal
    from app.models.spc import InspectionCharacteristic, SPCAlarm
    from app.models.supplier import Supplier, SupplierEvaluation

    now = datetime.now(UTC)
    pkg = {
        "generated_at": now.isoformat(),
        "product_line_code": product_line_code,
    }

    # 1. Quality goals
    qg_base = select(func.count()).select_from(QualityGoal).where(QualityGoal.status == "active")
    if product_line_code:
        qg_base = qg_base.where(QualityGoal.product_line == product_line_code)
    total_goals = (await db.execute(qg_base)).scalar() or 0

    achieved = 0
    behind = 0
    if total_goals > 0:
        active_q = select(QualityGoal).where(QualityGoal.status == "active")
        if product_line_code:
            active_q = active_q.where(QualityGoal.product_line == product_line_code)
        active_goals = (await db.execute(active_q)).scalars().all()
        for g in active_goals:
            if not g.actual_value:
                behind += 1
                continue
            try:
                tv = g.target_value.strip()
                av = g.actual_value.strip()
                threshold = float(tv.lstrip("≥≤<>=").replace("%", "").replace("≤", "").replace("≥", ""))
                actual = float(av.replace("%", ""))
                if tv.startswith(("≥", ">=")):
                    achieved += 1 if actual >= threshold else 0
                    if actual < threshold:
                        behind += 1
                else:
                    achieved += 1 if actual <= threshold else 0
                    if actual > threshold:
                        behind += 1
            except (ValueError, TypeError):
                pass
    pkg["quality_goals"] = {
        "total": total_goals,
        "achieved": achieved,
        "on_track": total_goals - achieved - behind,
        "behind": behind,
    }

    # 2. Internal audits
    finding_base = select(func.count()).select_from(AuditFinding)
    closed_f = (await db.execute(
        finding_base.where(AuditFinding.status == "closed")
    )).scalar() or 0
    total_f = (await db.execute(finding_base)).scalar() or 0
    pkg["internal_audits"] = {
        "total_findings": total_f,
        "closed_findings": closed_f,
        "open_findings": total_f - closed_f,
        "closure_rate": round(closed_f / total_f, 3) if total_f else 0,
    }

    # 3. CAPA stats
    capa_base = select(func.count()).select_from(CAPAEightD)
    if product_line_code:
        capa_base = capa_base.where(CAPAEightD.product_line_code == product_line_code)
    total_capa = (await db.execute(capa_base)).scalar() or 0
    open_capa = (await db.execute(
        capa_base.where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]))
    )).scalar() or 0
    closed_capa = total_capa - open_capa
    pkg["capa_stats"] = {
        "total": total_capa,
        "open": open_capa,
        "closed": closed_capa,
    }

    # 4. FMEA risks
    fmea_base = select(func.count()).select_from(FMEADocument)
    if product_line_code:
        fmea_base = fmea_base.where(FMEADocument.product_line_code == product_line_code)
    total_fmea = (await db.execute(fmea_base)).scalar() or 0

    fmea_docs_q = select(FMEADocument.fmea_id, FMEADocument.status, FMEADocument.graph_data)
    if product_line_code:
        fmea_docs_q = fmea_docs_q.where(FMEADocument.product_line_code == product_line_code)
    fmea_docs = (await db.execute(fmea_docs_q)).all()

    status_dist: dict[str, int] = {}
    high_ap = 0
    for _, status, gd in fmea_docs:
        status_dist[status] = status_dist.get(status, 0) + 1
        if gd and isinstance(gd, dict):
            for node in gd.get("nodes", []):
                if node.get("ap") == "H":
                    high_ap += 1
    pkg["fmea_risks"] = {
        "total_documents": total_fmea,
        "high_ap_count": high_ap,
        "status_distribution": status_dist,
    }

    # 5. SPC capability
    ic_base = select(func.count()).select_from(InspectionCharacteristic)
    if product_line_code:
        ic_base = ic_base.where(InspectionCharacteristic.product_line == product_line_code)
    total_charts = (await db.execute(ic_base)).scalar() or 0

    alarm_base = select(func.count()).select_from(SPCAlarm)
    if product_line_code:
        alarm_base = alarm_base.join(
            InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id
        ).where(InspectionCharacteristic.product_line == product_line_code)
    total_alarms = (await db.execute(alarm_base)).scalar() or 0
    pkg["spc_capability"] = {
        "total_control_charts": total_charts,
        "out_of_control_events": total_alarms,
    }

    # 6. Supplier performance
    total_sup = (await db.execute(
        select(func.count()).select_from(Supplier)
    )).scalar() or 0
    eval_base = select(SupplierEvaluation.grade, func.count()).group_by(SupplierEvaluation.grade)
    eval_rows = (await db.execute(eval_base)).all()
    grade_dist = {row[0]: row[1] for row in eval_rows}
    avg_del = (await db.execute(
        select(func.avg(SupplierEvaluation.delivery_score))
    )).scalar()
    pkg["supplier_performance"] = {
        "total_suppliers": total_sup,
        "rating_distribution": grade_dist,
        "avg_delivery_score": round(float(avg_del), 1) if avg_del else None,
    }

    # 7. Previous review actions
    prev_outputs = (await db.execute(
        select(ReviewOutput.status, func.count())
        .group_by(ReviewOutput.status)
    )).all()
    prev_dist = {row[0]: row[1] for row in prev_outputs}
    total_out = sum(prev_dist.values())
    pkg["previous_review_actions"] = {
        "total_outputs": total_out,
        "completed": prev_dist.get("completed", 0) + prev_dist.get("verified", 0),
        "verified": prev_dist.get("verified", 0),
        "in_progress": prev_dist.get("in_progress", 0),
        "pending": prev_dist.get("pending", 0),
        "completion_rate": round(
            (prev_dist.get("completed", 0) + prev_dist.get("verified", 0)) / total_out, 3
        ) if total_out else 0,
    }

    return pkg


async def list_outputs(
    db: AsyncSession, review_id: uuid.UUID,
) -> list[ReviewOutput]:
    result = await db.execute(
        select(ReviewOutput)
        .where(ReviewOutput.review_id == review_id)
        .order_by(ReviewOutput.created_at)
    )
    return list(result.scalars().all())


async def create_output(
    db: AsyncSession,
    review_id: uuid.UUID,
    *,
    category: str,
    description: str,
    responsible_id: uuid.UUID | None,
    due_date=None,
    user_id: uuid.UUID,
) -> ReviewOutput:
    review = await get_review(db, review_id)
    if review is None:
        raise ValueError("review not found")
    if review.status != "in_review":
        raise ValueError("can only add outputs in in_review status")

    output = ReviewOutput(
        review_id=review_id,
        category=category,
        description=description,
        responsible_id=responsible_id,
        due_date=due_date,
    )
    db.add(output)
    await _audit(db, "CREATE", output.output_id, user_id, {
        "review_id": str(review_id),
        "category": category,
        "description": description[:100],
    }, table_name="review_outputs")
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(_parse_integrity_error(e, "创建措施"))
    await db.refresh(output)
    return output


async def update_output(
    db: AsyncSession,
    output: ReviewOutput,
    *,
    review_is_closed: bool,
    user_id: uuid.UUID,
    **fields,
) -> ReviewOutput:
    if review_is_closed:
        allowed = {"status", "completion_notes", "verified_by", "verified_at", "verification_notes"}
        for k in fields:
            if k not in allowed:
                raise ValueError(f"field '{k}' is locked after review is closed")

    # Validate status transitions: pending → in_progress → completed → verified
    new_status = fields.get("status")
    if new_status is not None and new_status != output.status:
        valid_transitions = {
            "pending": "in_progress",
            "in_progress": "completed",
            "completed": "verified",
        }
        expected = valid_transitions.get(output.status)
        if expected is None or new_status != expected:
            raise ValueError(f"invalid status transition: {output.status} → {new_status}")

    changed = {}
    for f, val in fields.items():
        if val is None:
            continue
        old = getattr(output, f)
        if val != old:
            changed[f] = {"before": old, "after": val}
            setattr(output, f, val)

    if not changed:
        return output

    await _audit(db, "UPDATE", output.output_id, user_id, changed, table_name="review_outputs")
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(_parse_integrity_error(e, "更新措施"))
    await db.refresh(output)
    return output


async def delete_output(
    db: AsyncSession, output: ReviewOutput, user_id: uuid.UUID,
) -> None:
    review = await get_review(db, output.review_id)
    if review and review.status not in ("in_review", "data_collected"):
        raise ValueError("can only delete outputs in data_collected or in_review status")
    await _audit(db, "DELETE", output.output_id, user_id, {
        "review_id": str(output.review_id),
        "category": output.category,
    }, table_name="review_outputs")
    try:
        await db.delete(output)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("cannot delete output")


async def verify_output(
    db: AsyncSession,
    output: ReviewOutput,
    *,
    verification_notes: str,
    user_id: uuid.UUID,
) -> ReviewOutput:
    if output.status != "completed":
        raise ValueError("only completed outputs can be verified")
    if not verification_notes.strip():
        raise ValueError("verification_notes is required")

    output.status = "verified"
    output.verified_by = user_id
    output.verified_at = datetime.now(UTC).date()
    output.verification_notes = verification_notes

    await _audit(db, "TRANSITION", output.output_id, user_id, {
        "status": {"before": "completed", "after": "verified"},
        "verified_by": str(user_id),
    }, table_name="review_outputs")
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(_parse_integrity_error(e, "效果验证"))
    await db.refresh(output)
    return output