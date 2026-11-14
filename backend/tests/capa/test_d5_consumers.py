"""Actual D5 consumer regressions: restricted text must not become legacy."""
from types import SimpleNamespace
import pytest
from sqlalchemy import update
from app.models.role import RolePermission
from tests.capa.test_d5_measure_visibility import d5_case
from tests.services.agent_runtime.conftest import committed_runtime

pytestmark = pytest.mark.requires_db

@pytest.mark.asyncio
async def test_full_material_requires_every_source_before_body(d5_case):
    from app.services.capa_d5_measures import full_d5_material
    from tests.capa.test_d4_source_access import SQLSpy
    c = d5_case
    for scope in c.actors[:2]:
        with SQLSpy(await c.db.connection()) as spy:
            with pytest.raises(PermissionError):
                await full_d5_material(c.db, c.report, scope=scope)
        assert not any('final_text' in sql for sql in spy.statements)
    material = await full_d5_material(c.db, c.report, scope=c.actors[2])
    assert {row['final_text'] for row in material} == {'secret final 1', 'secret final 2'}
    material.sort(key=lambda row: row['final_text'])
    assert len(material[1]['sources']) == 2
    assert material[0]['measure_id'] == str(c.measures[0])

@pytest.mark.asyncio
async def test_full_ppt_requires_current_complete_authority(d5_case):
    from app.services.capa_ppt_service import generate_content
    c = d5_case
    with pytest.raises(PermissionError):
        await generate_content(c.db, c.report.report_id, scope=c.actors[1])
    content = await generate_content(c.db, c.report.report_id, scope=c.actors[2])
    d5 = next(p for p in content.pages if p.title.startswith('D5'))
    assert 'secret final 2' in str(d5.sections)
    assert c.report.d5_correction == 'ordinary legacy D5'

@pytest.mark.asyncio
async def test_restricted_only_d5_advances_without_legacy_copy(d5_case):
    from app.services.capa_service import advance_capa
    c = d5_case
    c.report.d5_correction = None
    await c.db.commit()
    result = await advance_capa(c.db, c.report, c.user_id)
    assert result.status == 'D6_VERIFICATION'
    assert result.d5_correction is None

@pytest.mark.asyncio
async def test_model_path_without_item_recipient_contract_is_unavailable(d5_case):
    from app.services.capa_doc_gate_service import generate_impact_analysis
    c = d5_case
    c.report.status = 'D8_GATE_PENDING'
    await c.db.commit()
    with pytest.raises(PermissionError, match='D5_FULL_MATERIAL_UNAVAILABLE'):
        await generate_impact_analysis(c.db, c.report, c.user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['empty', 'malformed'])
async def test_d5_business_completeness_requires_real_formal_material(d5_case, change):
    from sqlalchemy import delete
    from app.models.capa_d5_proposal import CapaD5Measure, CapaD5ProposalSource
    from app.services.capa_service import advance_capa
    c = d5_case
    c.report.d5_correction = None
    if change == 'empty':
        await c.db.execute(delete(CapaD5Measure))
    else:
        await c.db.execute(delete(CapaD5ProposalSource))
    await c.db.commit()
    with pytest.raises(ValueError):
        await advance_capa(c.db, c.report, c.user_id)


@pytest.mark.asyncio
async def test_full_material_does_not_silently_drop_malformed_formal_measure(d5_case):
    from sqlalchemy import delete
    from app.models.capa_d5_proposal import CapaD5ProposalSource
    from app.services.capa_d5_measures import full_d5_material
    c = d5_case
    await c.db.execute(delete(CapaD5ProposalSource).where(CapaD5ProposalSource.proposal_id == c.proposals[1]))
    await c.db.commit()
    with pytest.raises(PermissionError):
        await full_d5_material(c.db, c.report, scope=c.actors[2])


@pytest.mark.asyncio
async def test_legacy_knowledge_and_background_embedding_exclude_formal_text(d5_case, monkeypatch):
    from app.services.knowledge_sink_service import _assemble_deterministic_fields
    from app.services.embedding_sync_worker import fetch_chunks, process_batch_once
    from app.models.document_embedding import EmbeddingSyncOutbox
    c = d5_case
    qualify_test_vector_namespace(c.db, monkeypatch)
    fields = await _assemble_deterministic_fields(c.db, c.report)
    assert fields['d5'] == 'ordinary legacy D5'
    assert 'secret final' not in str(fields)
    chunks = await fetch_chunks(c.db, [{'entity_type': 'capa', 'entity_id': c.report.report_id}])
    assert any(row['chunk_text'] == 'ordinary legacy D5' for row in chunks)
    assert 'secret final' not in str(chunks)
    c.db.add(EmbeddingSyncOutbox(entity_type='capa', entity_id=c.report.report_id,
        factory_id=c.report.factory_id, product_line_code=c.report.product_line_code))
    await c.db.commit()
    class ExternalEmbedding:
        model_name = 'deterministic-test-only'
        async def embed(self, texts):
            assert 'secret final' not in str(texts)
            assert 'ordinary legacy D5' in texts
            return [[1.0] + [0.0] * 1535 for _ in texts]
    assert await process_batch_once(c.db, ExternalEmbedding())


@pytest.mark.asyncio
async def test_historical_sources_exclude_formal_text(d5_case, monkeypatch):
    from sqlalchemy import text
    from uuid import uuid4
    from app.services.recommendation_sources import HistoricalCAPASource, HistoricalCAPAMeasureSource
    from app.services.lessons_learned.sources.historical_capa import LessonsCAPASource
    from app.services.lessons_learned.context import LessonsLearnedContext
    c = d5_case
    qualify_test_vector_namespace(c.db, monkeypatch)
    c.report.status = 'D8_CLOSURE'
    await c.db.commit()
    vec = '[' + ','.join(['1']+['0']*1535) + ']'
    for field in ('d2_description', 'd4_root_cause'):
        await c.db.execute(text("""INSERT INTO document_embeddings
            (id,entity_type,entity_id,entity_field,chunk_text,embedding,embedding_model,factory_id,product_line_code)
            VALUES (:id,'capa',:rid,:field,'legacy problem',CAST(:vec AS vector),'fixture',:fid,:line)"""),
            dict(id=uuid4(), rid=c.report.report_id, field=field, vec=vec, fid=c.report.factory_id, line=c.report.product_line_code))
    await c.db.commit()
    for cls, field in [(HistoricalCAPASource, 'd2_description'), (HistoricalCAPAMeasureSource, 'd4_root_cause')]:
        result = await cls(c.db, None)._search(vec, [c.report.product_line_code], field, 10, c.report.factory_id)
        assert result and 'ordinary legacy D5' in str(result)
        assert 'secret final' not in str(result)
    class ExternalEmbedding:
        async def embed(self, texts):
            return [[1.0]+[0.0]*1535]
    ctx = LessonsLearnedContext('capa', uuid4(), 'problem', None, None, c.report.product_line_code,
        [c.report.product_line_code])
    result = await LessonsCAPASource(c.db, ExternalEmbedding()).retrieve(ctx)
    assert result and 'ordinary legacy D5' in str(result)
    assert 'secret final' not in str(result)


def qualify_test_vector_namespace(db, monkeypatch):
    """Test adapter for an existing tenant extension-lookup limitation.

    Only the pgvector type/operator are qualified; business SQL still executes
    in the original isolated tenant. This is not a production-tenant vector pass.
    """
    from sqlalchemy.sql.elements import TextClause
    from sqlalchemy import text
    execute = db.execute
    async def qualified(statement, *args, **kwargs):
        if isinstance(statement, TextClause):
            statement = text(str(statement).replace(' AS vector)', ' AS public.vector)')
                .replace(' <=> ', ' OPERATOR(public.<=>) '))
        return await execute(statement, *args, **kwargs)
    monkeypatch.setattr(db, 'execute', qualified)


@pytest.mark.asyncio
@pytest.mark.parametrize('consumer', ['draft', 'd7-auto-fill', 'ppt-model'])
async def test_existing_consumers_without_item_acl_refuse_full_material(d5_case, consumer):
    c = d5_case
    with pytest.raises(PermissionError, match='D5_FULL_MATERIAL_UNAVAILABLE'):
        if consumer == 'draft':
            from app.services.capa_draft_service import generate_draft
            await generate_draft(c.db, c.report.report_id, 'd6', None, None, None)
        elif consumer == 'd7-auto-fill':
            from app.services.capa_d7_action_service import auto_fill_d7
            c.report.status = 'D7_PREVENTION'
            await c.db.commit()
            await auto_fill_d7(c.db, c.report, None, SimpleNamespace(user_id=c.user_id))
        else:
            from app.services.capa_ppt_review_service import review_and_correct
            await review_and_correct(c.db, c.report.report_id, object(), c.binding.schema_name,
                scope=c.actors[2])


@pytest.mark.asyncio
async def test_ppt_rechecks_d5_authority_after_later_material_queries(d5_case, monkeypatch):
    from app.services.capa_ppt_service import generate_content
    c = d5_case
    execute = c.db.execute
    revoked = False
    async def revoke(statement, *args, **kwargs):
        nonlocal revoked
        result = await execute(statement, *args, **kwargs)
        if not revoked and 'FROM capa_d7_node_action' in str(statement):
            revoked = True
            async with c.factory(binding=c.binding) as writer:
                await writer.execute(update(RolePermission).where(RolePermission.role_id == c.actors[2].role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await writer.commit()
        return result
    monkeypatch.setattr(c.db, 'execute', revoke)
    with pytest.raises(PermissionError):
        await generate_content(c.db, c.report.report_id, scope=c.actors[2])
    assert revoked
