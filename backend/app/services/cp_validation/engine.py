"""Control Plan Validation Engine — orchestrates rule execution with two-table persistence.

findings  = stable identity (hash uses business keys) + inherited user state
occurrences = per-run snapshot of what was detected (only present=true records)
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.cp_validation import (
    CPValidationRun,
    CPValidationFinding,
    CPValidationOccurrence,
    compute_finding_hash,
)
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.services.cp_validation.rule_engine import run_all_rules

logger = logging.getLogger(__name__)

STALE_RUN_TIMEOUT = timedelta(minutes=5)




class ValidationAlreadyRunning(Exception):
    """Raised when a validation run is already in progress for this CP."""
    pass


class CPValidationEngine:

    async def validate(
        self,
        db: AsyncSession,
        cp_id: uuid.UUID,
        user_id: uuid.UUID,
        trigger: str = "manual",
    ) -> CPValidationRun:
        # 1. Handle stale running runs (crashed worker, OOM, etc.)
        await self._fail_stale_runs(db, cp_id)

        # 2. Create run (may raise IntegrityError if concurrent)
        run = CPValidationRun(
            cp_id=cp_id,
            trigger=trigger,
            status="running",
            created_by=user_id,
        )
        db.add(run)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise ValidationAlreadyRunning(f"Validation already running for CP {cp_id}")

        await db.refresh(run)

        try:
            await self._execute_validation(db, run)
        except Exception:
            logger.exception("Validation run %s failed", run.run_id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise

        return run

    async def _fail_stale_runs(self, db: AsyncSession, cp_id: uuid.UUID) -> None:
        """Mark runs that have been 'running' for >5 min as failed."""
        cutoff = datetime.now(timezone.utc) - STALE_RUN_TIMEOUT
        result = await db.execute(
            select(CPValidationRun).where(
                CPValidationRun.cp_id == cp_id,
                CPValidationRun.status == "running",
                CPValidationRun.started_at < cutoff,
            )
        )
        stale = result.scalars().all()
        for run in stale:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.failed_rules = (run.failed_rules or []) + ["timeout"]
            logger.warning("Marked stale run %s as failed", run.run_id)

    async def _execute_validation(self, db: AsyncSession, run: CPValidationRun) -> None:
        cp_id = run.cp_id

        cp_result = await db.execute(
            select(ControlPlan).where(ControlPlan.cp_id == cp_id)
        )
        cp = cp_result.scalar_one_or_none()
        if cp is None:
            raise ValueError(f"Control plan {cp_id} not found")

        items_result = await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id)
        )
        items = list(items_result.scalars().all())

        fmea_graph: dict | None = None
        if cp.fmea_ref_id:
            fmea_result = await db.execute(
                select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id)
            )
            fmea = fmea_result.scalar_one_or_none()
            if fmea:
                fmea_graph = fmea.graph_data

        findings, failed_rules = run_all_rules(cp, items, fmea_graph)

        # Load existing findings for this CP
        existing_result = await db.execute(
            select(CPValidationFinding).where(CPValidationFinding.cp_id == cp_id)
        )
        existing_by_hash = {row.finding_hash: row for row in existing_result.scalars().all()}

        error_count = 0
        warning_count = 0
        info_count = 0

        for finding in findings:
            h = compute_finding_hash(finding.rule_id, finding.stable_key, finding.key_content)

            existing = existing_by_hash.get(h)
            if existing is None:
                existing = CPValidationFinding(
                    cp_id=cp_id,
                    finding_hash=h,
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    category=finding.category,
                    status="open",
                )
                db.add(existing)
                await db.flush()
                await db.refresh(existing)
                existing_by_hash[h] = existing

            # Create occurrence (always present=true — we only record what IS found)
            db.add(CPValidationOccurrence(
                run_id=run.run_id,
                finding_id=existing.finding_id,
                cp_id=cp_id,
                validation_type="rule",
                title=finding.title,
                description=finding.description,
                affected_items=[finding.item_id] if finding.item_id else [],
                present=True,
            ))

            if finding.severity == "error":
                error_count += 1
            elif finding.severity == "warning":
                warning_count += 1
            else:
                info_count += 1

        run.status = "completed"
        run.rule_count = len(findings)
        run.error_count = error_count
        run.warning_count = warning_count
        run.info_count = info_count
        run.failed_rules = failed_rules
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
