"""Conservative protection for automatic CP sync only (2026-11-02 policy).

Readers never lock CAPA roots. Publishers take analysis/root locks before CP
parents, in UUID order; sync takes only CP parents and reads committed material.
"""
from __future__ import annotations

import uuid
import json
from collections import Counter
from sqlalchemy import select

from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.special_characteristic import SpecialCharacteristic
from app.state_machines.eightd_state import EightDState, is_capa_open_value


def row_material(row):
    return {c.name: str(v) if isinstance(v := getattr(row, c.name), uuid.UUID) else v
            for c in ControlPlanItem.__table__.columns}


async def cp_input_state(db, factory_id, product_line_code, *, lock=False):
    """Live CP material fingerprint, separate from CAPA's baseline-only C9 hash.

    Called before external calculation and again under parent locks at publish.
    No database locks are held during external calculation.
    """
    from app.services.version_service import compute_snapshot_hash
    cps = list((await db.scalars(select(ControlPlan).where(
        ControlPlan.factory_id == factory_id, ControlPlan.product_line_code == product_line_code
    ).order_by(ControlPlan.cp_id).execution_options(populate_existing=True))).all())
    if lock:
        for cp in cps:
            await db.execute(select(ControlPlan.cp_id).where(ControlPlan.cp_id == cp.cp_id).with_for_update())
        # Re-read after waiting; never publish using a cached ORM row.
        for cp in cps:
            await db.refresh(cp)
    result = []
    for cp in cps:
        items = list((await db.scalars(select(ControlPlanItem).where(
            ControlPlanItem.cp_id == cp.cp_id).order_by(ControlPlanItem.item_id)
            .execution_options(populate_existing=True))).all())
        latest = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id)
                                 .order_by(ControlPlanVersion.major_no.desc(), ControlPlanVersion.minor_no.desc()).limit(1))
        result.append({'cp_id': str(cp.cp_id), 'lock': cp.lock_version, 'status': cp.status,
                       'factory_id': str(cp.factory_id), 'product_line': cp.product_line_code,
                       'version': str(latest.version_id) if latest else None,
                       'hash': latest.sha256_hash if latest else None,
                       'rows': [row_material(i) for i in items]})
    return compute_snapshot_hash(result)


async def lock_analysis_inputs(db, analysis):
    """Serialize current-analysis material writers: analysis, then all CPs.

    Revalidate current identity after waiting. Used by audit/defer/confirm/waiver.
    """
    await db.refresh(analysis, with_for_update=True)
    if not analysis.is_current or analysis.status != 'done':
        raise ValueError('影响分析已替换，请重新生成影响分析')
    capa = await db.get(CAPAEightD, analysis.capa_id, populate_existing=True)
    await cp_input_state(db, capa.factory_id, capa.product_line_code, lock=True)


async def sync_protection(db, cp, items):
    """Return row codes and an opaque freshness binding, never CAPA details."""
    from app.services.version_service import compute_snapshot_hash, verify_cp_version
    def same_cp(value):
        try:
            return uuid.UUID(str(value)) == cp.cp_id
        except (ValueError, TypeError, AttributeError):
            return False

    current_ids = {str(i.item_id) for i in items}
    protected = set()
    unresolved = False
    binding = []
    capas = list((await db.scalars(select(CAPAEightD).where(
        CAPAEightD.factory_id == cp.factory_id,
        CAPAEightD.product_line_code == cp.product_line_code
    ).order_by(CAPAEightD.report_id).execution_options(populate_existing=True))).all())

    async def version_rows(meta, *, decision=False):
        if not isinstance(meta, dict):
            raise ValueError('version material')
        raw_id = meta.get('version_after_id' if decision else 'version_id')
        if decision and raw_id is None and meta.get('sha256') is None:
            return  # normal pending_update with no actual version binding
        vid = uuid.UUID(str(raw_id))
        version = await db.scalar(select(ControlPlanVersion).where(
            ControlPlanVersion.version_id == vid, ControlPlanVersion.cp_id == cp.cp_id,
            ControlPlanVersion.factory_id == cp.factory_id))
        if version is None or meta.get('sha256') != version.sha256_hash or not await verify_cp_version(db, vid):
            raise ValueError('version integrity')
        snapshot = version.items_snapshot
        if isinstance(snapshot, dict):
            snapshot = snapshot['items']
        if not isinstance(snapshot, list):
            raise ValueError('version rows')
        for row in snapshot:
            protected.add(str(uuid.UUID(str(row['item_id']))))

    def targets(points, document):
        # Validate persisted shapes without the publisher's repair/coercion of
        # LLM output. Malformed known-CP material is never absence of a target.
        from app.services.capa_doc_gate_service import _CP_ADD_FIELDS, _ALLOWED_NODE_TYPES
        if not isinstance(points, list):
            raise ValueError('key points')
        for kp in points:
            if not isinstance(kp, dict):
                raise ValueError('key point')
            kind, action = kp.get('target_kind'), kp.get('expected_action')
            if action not in ('add', 'modify', 'delete') or kind not in ('document', 'cp_item'):
                raise ValueError('CP key point discriminant')
            if kind == 'document':
                if (action != 'add' or 'target_key' in kp or 'add_anchor' in kp
                        or document.get('baseline_version') is not None
                        or document.get('baseline_version_id') is not None):
                    raise ValueError('document add shape')
                continue  # legitimate document-add intent does not protect old rows
            field = kp.get('field')
            if not isinstance(field, str) or field not in _CP_ADD_FIELDS:
                raise ValueError('CP key point field')
            if action in ('modify', 'delete'):
                if 'target_key' not in kp or 'add_anchor' in kp:
                    raise ValueError('CP target shape')
                protected.add(str(uuid.UUID(str(kp['target_key']))))
            else:
                anchor = kp.get('add_anchor')
                if 'target_key' in kp or not isinstance(anchor, dict):
                    raise ValueError('CP add shape')
                if (any(not isinstance(anchor.get(k), str) or not anchor[k].strip()
                        for k in ('parent_node_id', 'node_type', 'business_key'))
                        or anchor['node_type'] not in _ALLOWED_NODE_TYPES):
                    raise ValueError('CP add anchor')


    for capa in capas:
        if capa.status not in {s.value for s in EightDState}:
            unresolved = True
            binding.append([str(capa.report_id), 'unknown'])
            continue
        if not is_capa_open_value(capa.status):
            continue
        analyses = list((await db.scalars(select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current.is_(True),
            CapaDocgAnalysis.status == 'done').execution_options(populate_existing=True))).all())
        for a in analyses:
            docs = a.affected_docs
            # Only known references to this CP participate; malformed known material fails closed.
            if not isinstance(docs, list):
                unresolved = True
                binding.append([str(a.analysis_id), 'invalid'])
                continue
            own = [d for d in docs if isinstance(d, dict) and d.get('doc_type') == 'control_plan'
                   and same_cp(d.get('doc_id'))]
            decision = await db.scalar(select(CapaDocgDecision).where(
                CapaDocgDecision.analysis_id == a.analysis_id).order_by(CapaDocgDecision.revision.desc())
                .limit(1).execution_options(populate_existing=True))
            audits = list((await db.scalars(select(CapaDocgAudit).where(
                CapaDocgAudit.analysis_id == a.analysis_id).order_by(CapaDocgAudit.audited_at.desc())
                .execution_options(populate_existing=True))).all())
            if decision:
                audits = [x for x in audits if x.audit_run_id == decision.audit_run_id] if decision.audit_run_id else []
            elif audits:
                newest = audits[0].audited_at
                batches = {x.audit_run_id for x in audits if x.audited_at == newest}
                if len(batches) != 1:
                    if own:
                        unresolved = True
                    audits = []
                else:
                    batch = next(iter(batches))
                    audits = [x for x in audits if x.audit_run_id == batch]
            own_audits = [x for x in audits if x.doc_type == 'control_plan' and x.doc_id == cp.cp_id]
            snapshots = decision.version_snapshot if decision else []
            own_snapshots = [s for s in snapshots if isinstance(s, dict) and s.get('doc_type') == 'control_plan'
                             and same_cp(s.get('doc_id'))] if isinstance(snapshots, list) else []
            if not (own or own_audits or own_snapshots):
                continue
            binding.append({'capa': str(capa.report_id), 'status': capa.status, 'analysis': str(a.analysis_id),
                            'docs': docs, 'revision': decision.revision if decision else None,
                            'snapshot': snapshots, 'batch': str(decision.audit_run_id) if decision else None,
                            'audits': [{'id': str(x.audit_id), 'coverage': x.coverage,
                                        'before': x.version_before, 'after': x.version_after} for x in own_audits]})
            try:
                if len(analyses) != 1 or len(own) > 1 or not isinstance(snapshots, list):
                    raise ValueError('ambiguous material')
                for doc in own:
                    targets(doc['key_points'], doc)
                if (decision and decision.audit_run_id) or audits:
                    expected = {(d['doc_type'], str(uuid.UUID(str(d['doc_id'])))) for d in docs}
                    actual = {(x.doc_type, str(x.doc_id)) for x in audits}
                    if expected != actual or len(actual) != len(audits):
                        raise ValueError('incomplete audit batch')
                for audit in own_audits:
                    if not isinstance(audit.coverage, list):
                        raise ValueError('coverage')
                    points = [c['key_point'] for c in audit.coverage]
                    expected_points = own[0]['key_points'] if len(own) == 1 else None
                    if (expected_points is None or audit.total_count != len(points)
                            or audit.covered_count != sum(c.get('covered') is True for c in audit.coverage)
                            or any(not isinstance(c.get('covered'), bool) for c in audit.coverage)
                            or Counter(json.dumps(k, sort_keys=True) for k in points)
                            != Counter(json.dumps(k, sort_keys=True) for k in expected_points)):
                        raise ValueError('incomplete coverage')
                    targets(points, own[0])
                    for meta in (audit.version_before, audit.version_after):
                        if meta is not None:
                            await version_rows(meta)
                for meta in own_snapshots:
                    await version_rows(meta, decision=True)
            except (ValueError, TypeError, KeyError, AttributeError):
                unresolved = True
    links = list((await db.scalars(select(SpecialCharacteristic).where(
        SpecialCharacteristic.cp_item_id.in_([i.item_id for i in items]))
        .order_by(SpecialCharacteristic.sc_id).execution_options(populate_existing=True))).all()) if items else []
    linked = {str(x.cp_item_id) for x in links}
    codes = {iid: [] for iid in current_ids}
    for iid in current_ids:
        if unresolved:
            codes[iid].append('protection_state_unresolved')
        if iid in protected:
            codes[iid].append('protected_capa_material')
    execution = linked | {str(i.item_id) for i in items if i.spc_chart_id or i.gauge_id}
    return codes, execution, compute_snapshot_hash({'material': binding, 'links': [
        [str(x.sc_id), str(x.cp_item_id), str(x.factory_id), x.product_line_code] for x in links],
                                                     'unresolved': unresolved})
