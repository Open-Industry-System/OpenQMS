"""Advisory characteristic rules and per-control-row finding identities."""
from types import SimpleNamespace
import uuid

from app.services.cp_validation.rule_engine import run_all_rules


def item(**changes):
    fields = dict(item_id=uuid.uuid4(), source_fmea_node_id='s1', step_no='OP10',
        process_name='Check', product_characteristic='Diameter', process_characteristic=None,
        special_class='CC', control_method='Measure', evaluation_method='Gauge',
        reaction_plan='Contain', specification_tolerance='10 ± 0.1 mm', sort_order=0)
    fields.update(changes)
    return SimpleNamespace(**fields)


def rules(rows):
    findings, failed = run_all_rules(None, rows, None)
    assert failed == []
    return findings


def test_missing_specification_is_warning_not_a_gate():
    f = rules([item(specification_tolerance='  ')])
    assert [(x.rule_id, x.severity) for x in f] == [('R005', 'warning')]


def test_controlled_reference_and_qualitative_requirements_are_valid_without_type_guessing():
    assert rules([item(specification_tolerance='见受控图纸 DWG-17 rev B'),
                  item(specification_tolerance='外观无裂纹', product_characteristic='速度')]) == []


def test_legacy_dual_object_is_advisory_not_automatically_fixed():
    row = item(process_characteristic='Pressure')
    assert [(x.rule_id, x.severity) for x in rules([row])] == [('R006', 'warning')]
    assert row.product_characteristic == 'Diameter' and row.process_characteristic == 'Pressure'


def test_finding_identity_is_per_row_and_source_not_name_or_order():
    ref = dict(mapping_version=1, fmea_id=str(uuid.uuid4()), step_id='s1', function_id='sf1',
               characteristic_id=str(uuid.uuid4()))
    a = item(source_characteristic_ref=ref, control_method='', specification_tolerance='')
    b = item(source_characteristic_ref=ref, control_method='', specification_tolerance='')
    findings = rules([a, b])
    for rule_id in ('R001', 'R004', 'R005'):
        keys = [f.stable_key for f in findings if f.rule_id == rule_id]
        assert len(keys) == len(set(keys)) == 2
        assert all(str(ref['characteristic_id']) in k for k in keys)
    keys = [f.stable_key for f in findings]
    a.product_characteristic = 'Renamed'; a.sort_order = 999
    assert [f.stable_key for f in rules([a, b])] == keys
    a.source_characteristic_ref = {**ref, 'fmea_id': str(uuid.uuid4())}
    assert rules([a])[0].stable_key != keys[0]


def test_legacy_missing_new_fields_remains_supported_and_row_uuid_is_used():
    a, b = item(control_method=''), item(control_method='')
    keys = [f.stable_key for f in rules([a, b]) if f.rule_id == 'R001']
    assert len(set(keys)) == 2
    assert str(a.item_id) in keys[0]


import pytest


@pytest.mark.asyncio
async def test_same_source_controls_keep_independent_persisted_decisions_across_rename(db, admin_user):
    from sqlalchemy import select
    from app.models.control_plan import ControlPlan, ControlPlanItem
    from app.models.cp_validation import CPValidationFinding, CPValidationOccurrence
    from app.services.cp_validation.engine import CPValidationEngine

    cp = ControlPlan(cp_id=uuid.uuid4(), document_no='T9-VALID-'+uuid.uuid4().hex[:10], title='Validation',
        product_line_code='DC-DC-100', factory_id=admin_user.factory_id)
    db.add(cp); await db.flush()
    ref = dict(mapping_version=1, fmea_id=str(uuid.uuid4()), step_id='s1', function_id='sf1',
               characteristic_id=str(uuid.uuid4()))
    rows = [ControlPlanItem(item_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=cp.factory_id,
        step_no='OP10', source_fmea_node_id='s1', source_characteristic_ref=ref,
        product_characteristic='Same name', specification_tolerance='', control_method='Measure',
        evaluation_method='Gauge', reaction_plan='Contain') for _ in range(2)]
    db.add_all(rows); await db.flush()
    engine = CPValidationEngine()
    first = await engine.validate(db, cp.cp_id, admin_user.user_id)
    findings = list((await db.scalars(select(CPValidationFinding).where(
        CPValidationFinding.cp_id == cp.cp_id, CPValidationFinding.rule_id == 'R005'))).all())
    assert len(findings) == 2
    occurrences = list((await db.scalars(select(CPValidationOccurrence).where(
        CPValidationOccurrence.run_id == first.run_id))).all())
    selected = next(o.finding_id for o in occurrences if o.affected_items == [str(rows[0].item_id)])
    next(f for f in findings if f.finding_id == selected).status = 'accepted'
    rows[0].product_characteristic = 'Renamed'; rows[0].sort_order = 99
    await db.flush()
    second = await engine.validate(db, cp.cp_id, admin_user.user_id)
    assert second.error_count == 0 and second.warning_count == 2
    after = list((await db.scalars(select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id))).all())
    assert {f.finding_id for f in after} == {f.finding_id for f in findings}
    assert {f.finding_id: f.status for f in after} == {
        f.finding_id: 'accepted' if f.finding_id == selected else 'open' for f in findings}
