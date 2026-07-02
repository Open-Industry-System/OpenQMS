"""Fixed whitelist for E2E cleanup. NO string-concatenation of table/column names anywhere else.

Each parent entry: (model, pk_col_name, doc_no_col_name, [(child_model, child_fk_col_name), ...]).
Children are deleted first (FK reverse order), then the parent. All in one transaction.
Only models whose doc_no/name can carry an E2E- prefix are listed as parents.

FK ondelete analysis (verified against backend/app/models/*.py and alembic 020):
- FMEAVersion.fmea_id        → ondelete=CASCADE  → auto-deleted with parent. NOT listed.
- RecommendationCache.fmea_id → ondelete=CASCADE → auto-deleted with parent. NOT listed.
- RecommendationCache.report_id → ondelete=CASCADE → auto-deleted with parent. NOT listed.
- ChangeImpact.fmea_id      → ondelete=CASCADE  → auto-deleted with parent. NOT listed.
- ControlPlan.fmea_id        → no ondelete (NO ACTION), nullable. Could block parent delete
                              IF a spec links a control plan to an E2E FMEA. Not exercised
                              in M1; add as child when the control-plan spec (M2) links E2E FMEAs.
- CAPAEightD.fmea_ref_id     → no ondelete, nullable. Self-referential; not a child of FMEA
                              cleanup (cleanup deletes CAPA by its own document_no prefix).
- audit_finding.report_id    → no ondelete, nullable. Could block CAPA delete IF a spec
                              creates an audit finding referencing an E2E CAPA. Add as child
                              when the audit spec exercises this.

⚠️ VERSION-TABLE TRIGGER (alembic 020_snapshot_hash_trigger.py:60): `trg_fmea_version_no_update`
is `BEFORE UPDATE OR DELETE` and `prevent_version_tampering()` RAISES on delete. So when a spec
creates an FMEA version snapshot, CASCADE-deleting the parent FMEA will fail on the version row.
The cleanup endpoint handles this by DISABLE-ing the two no_update triggers for the duration of
its transaction (dedicated e2e DB, serialized workers:1), then re-enabling — see cleanup_test_data.
(M1 FMEA spec only asserts the snapshot entry is VISIBLE, does not click "create snapshot", so no
version row is created in M1; the trigger-disable is forward-robustness for later specs.)

AuditLog.entity_id is deliberately NOT a child: append-only, no unique constraint, type not
guaranteed to match a UUID in_ lookup, and leaving rows does NOT block re-runs (idempotent
seed keys on unique document_no). Cleaned by `make e2e-reset` (down -v)."""
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD

# Parents: (model, pk_col, doc_no_col, [(child_model, child_fk_col), ...])
# M0+M1: parents only — CASCADE handles version/recommendation-cache/change-impact children.
# Add a child entry ONLY when a later module links a NO-ACTION-FK child to an E2E parent
# (e.g. ControlPlan in M2, audit_finding in the audit module) — run that module's spec twice
# to confirm; if parent delete fails with FK violation, add the child here.
CLEANUP_PARENTS = [
    (FMEADocument, "fmea_id", "document_no", []),
    (CAPAEightD, "report_id", "document_no", []),
]
