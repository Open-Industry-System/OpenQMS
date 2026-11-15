"""A controlled root with no restricted D5 must remain controlled everywhere."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def controlled_root(r6_case):
    return await bind_controlled_root(r6_case)


async def bind_controlled_root(case):
    from app.models.capa import CAPAEightD
    from app.models.capa_r6 import CapaR6SourceOrigin
    from app.services.capa_d4_provenance import record_root_revision
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    actor = case.actor('edit')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        visible = await visible_fmea_source(db, SimpleNamespace(user=actor), case.source_a.fmea_id)
        source = CapaR6SourceOrigin(source_id=uuid4(), report_id=case.report_id,
            kind='fmea_projection', module='fmea', object_id=case.source_a.fmea_id,
            projection_id='fmea.failure_cause.reference.v1',
            version=await failure_cause_version(db, visible, 'cause'),
            factory_id=case.factory_id, product_line_code=case.line,
            fmea_id=case.source_a.fmea_id, node_id='cause')
        db.add(source)
        await db.flush()
        report.d4_root_cause = 'R6 protected root sentinel'
        report.title = 'R6 protected report'
        report.d2_description = 'Detailed problem description suitable for every retained draft step'
        report.d3_interim = 'Contain and inspect'
        report.d5_correction = 'Legacy correction'
        report.d6_verification = 'Legacy verification'
        report.d7_prevention = 'Legacy prevention'
        report.status = 'D4_ROOT_CAUSE'
        await record_root_revision(db, report_id=case.report_id, actor_id=actor.user_id,
            write_path='r6:test-consumer', added_source_ids=[source.source_id])
        await db.commit()
    return case


@pytest.mark.asyncio
async def test_legacy_material_guard_rejects_root_without_restricted_d5(controlled_root):
    from app.services.capa_d5_measures import require_legacy_d5_only
    async with controlled_root.session() as db:
        with pytest.raises(PermissionError, match='D4'):
            await require_legacy_d5_only(db, controlled_root.report_id)


@pytest.mark.asyncio
async def test_knowledge_copy_refuses_controlled_root(controlled_root):
    from app.models.capa import CAPAEightD
    from app.services.knowledge_sink_service import _assemble_deterministic_fields
    async with controlled_root.session() as db:
        report = await db.get(CAPAEightD, controlled_root.report_id)
        with pytest.raises(PermissionError, match='D4'):
            await _assemble_deterministic_fields(db, report)


@pytest.mark.asyncio
async def test_embedding_fetch_excludes_entire_controlled_report(controlled_root):
    from app.services.embedding_sync_worker import fetch_chunks
    async with controlled_root.session() as db:
        chunks = await fetch_chunks(db, [{'entity_type': 'capa', 'entity_id': controlled_root.report_id}])
        assert chunks == []


@pytest.mark.asyncio
async def test_root_inheritance_transaction_enqueues_old_index_invalidation(controlled_root):
    from sqlalchemy import select, func
    from app.models.document_embedding import EmbeddingSyncOutbox
    async with controlled_root.session() as db:
        count = await db.scalar(select(func.count()).select_from(EmbeddingSyncOutbox).where(
            EmbeddingSyncOutbox.entity_type == 'capa',
            EmbeddingSyncOutbox.entity_id == controlled_root.report_id))
        assert count > 0


@pytest.mark.asyncio
async def test_ppt_rechecks_all_root_sources_before_export(controlled_root):
    from app.services.capa_ppt_service import generate_content
    case = controlled_root
    actor = case.actor('edit')
    await actor.revoke('fmea')
    async with case.session() as db:
        with pytest.raises(PermissionError):
            await generate_content(db, case.report_id, scope=SimpleNamespace(user=actor))


@pytest.mark.asyncio
@pytest.mark.parametrize('outlet', ['lateral', 'doc_gate', 'd7'])
async def test_unsupported_derived_consumers_refuse_root(controlled_root, outlet):
    from app.models.capa import CAPAEightD
    case = controlled_root
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        with pytest.raises(PermissionError, match='D4'):
            if outlet == 'lateral':
                from app.services.capa_lateral_diffusion_service import build_source_snapshot
                await build_source_snapshot(db, report)
            elif outlet == 'doc_gate':
                from app.services.capa_doc_gate_service import generate_impact_analysis
                report.status = 'D8_GATE_PENDING'
                await generate_impact_analysis(db, report, case.actor('edit').user_id)
            else:
                from app.services.capa_d7_action_service import _compute_current_d7_recs
                await _compute_current_d7_recs(db, report)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', [None, 'missing', 'count', 'digest'])
async def test_old_index_rows_are_hidden_before_async_cleanup(controlled_root, monkeypatch, damage):
    from sqlalchemy import text, delete, update
    from app.models.capa import CAPAEightD
    from app.models.user import User
    from app.services.search_service import SearchService
    from app.services.recommendation_sources import HistoricalCAPASource, HistoricalCAPAMeasureSource
    from app.services.lessons_learned.sources.historical_capa import LessonsCAPASource
    from app.services.lessons_learned.context import LessonsLearnedContext
    from tests.capa.test_d5_consumers import qualify_test_vector_namespace
    case = controlled_root
    vector = [1.0] + [0.0] * 1535
    class Embedding:
        async def embed(self, texts):
            return [vector for _ in texts]
    async with case.session() as db:
        qualify_test_vector_namespace(db, monkeypatch)
        if damage:
            from app.models.capa_r6 import CapaR6RootRevisionBody, CapaR6RootRevisionSource
            await db.execute(text("SET LOCAL session_replication_role = 'replica'"))
            if damage == 'missing':
                await db.execute(delete(CapaR6RootRevisionBody).where(CapaR6RootRevisionBody.report_id == case.report_id))
            else:
                if damage == 'digest':
                    await db.execute(delete(CapaR6RootRevisionSource).where(CapaR6RootRevisionSource.report_id == case.report_id))
                await db.execute(update(CapaR6RootRevisionBody).where(CapaR6RootRevisionBody.report_id == case.report_id)
                    .values(binding_state='legacy_unattested', source_count=0, origin_digest='0' * 64))
            await db.commit()
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D8_CLOSURE'
        for field in ('d2_description', 'd4_root_cause'):
            await db.execute(text("""INSERT INTO document_embeddings
                (id,entity_type,entity_id,entity_field,chunk_text,embedding,embedding_model,factory_id,product_line_code)
                VALUES (:id,'capa',:rid,:field,'old unbound root copy',CAST(:vec AS vector),'fixture',:fid,:line)"""),
                dict(id=uuid4(), rid=case.report_id, field=field, vec=str(vector), fid=case.factory_id, line=case.line))
        await db.commit()
        # The row remains physically present; the current query boundary hides it.
        for cls, field in ((HistoricalCAPASource, 'd2_description'), (HistoricalCAPAMeasureSource, 'd4_root_cause')):
            assert await cls(db, None)._search(str(vector), [case.line], field, 5, case.factory_id) == []
        context = LessonsLearnedContext('capa', uuid4(), 'problem', None, 'serious', case.line, [case.line])
        assert await LessonsCAPASource(db, Embedding()).retrieve(context) == []
        user = await db.get(User, case.actor('edit').user_id)
        results = await SearchService(db, Embedding()).semantic_search('root', user, entity_types=['capa'])
        assert results.total == 0
        from sqlalchemy import event
        from app.services.embedding_sync_worker import fetch_chunks
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        connection = await db.connection()
        event.listen(connection.sync_connection, 'before_cursor_execute', capture)
        try:
            assert await fetch_chunks(db, [dict(entity_type='capa', entity_id=case.report_id)]) == []
        finally:
            event.remove(connection.sync_connection, 'before_cursor_execute', capture)
        assert not any('from capa_eightd' in sql and 'd4_root_cause' in sql for sql in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['d4-fmea-recommendations', 'd5-fmea-recommendations'])
async def test_old_recommendation_routes_refuse_controlled_root(controlled_root, path, monkeypatch):
    from app.main import app
    monkeypatch.setattr(app.state, 'embedding_provider', None, raising=False)
    case = controlled_root
    result = await case.actor('edit').client.get(f'/api/capa/{case.report_id}/{path}')
    assert result.status_code == 403, result.text


@pytest.mark.asyncio
@pytest.mark.parametrize('outlet', ['orchestrator', 'pipeline', 'fusion', 'scar'])
async def test_direct_legacy_outlets_reject_controlled_root(controlled_root, outlet):
    from app.services.recommendation_types import RecommendationContext
    case = controlled_root
    async with case.session() as db:
        context = RecommendationContext({'report_id': case.report_id, 'd4_root_cause': 'protected'}, [case.line], 'd5')
        with pytest.raises(PermissionError, match='D4'):
            if outlet == 'fusion':
                from app.services.llm_fusion_layer import LLMFusionLayer
                layer = LLMFusionLayer(None)
                layer.db = db
                await layer.enrich([], context)
            elif outlet == 'scar':
                from app.core.factory_scope import FactoryScope, ProductLineScope
                from app.core.deps import RequestScope
                from app.services.capa_scar_service import trigger_scar_from_capa
                scope = RequestScope(FactoryScope([case.factory_id], case.factory_id), case.factory_id,
                    ProductLineScope('SOME', [case.line]), case.actor('edit'))
                await trigger_scar_from_capa(db, case.report_id, supplier_id=uuid4(),
                    user_id=case.actor('edit').user_id, scope=scope)
            else:
                from app.services.recommendation_orchestrator import RecommendationOrchestrator
                from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
                cls = RecommendationOrchestrator if outlet == 'orchestrator' else HybridRecommendationPipeline
                service = cls(db, None, None)
                method = service.run if outlet == 'orchestrator' else service.recommend
                await method(context, user=case.actor('edit'), report_id=case.report_id,
                    factory_id=case.factory_id, tenant_schema=case.binding.schema_name)


@pytest.mark.asyncio
async def test_old_knowledge_and_lesson_copies_are_excluded(controlled_root, monkeypatch):
    from sqlalchemy import text
    from app.models.capa_lesson import CapaLessonLearned
    from app.models.knowledge_entry import KnowledgeEntry
    from app.services.recommendation_types import RecommendationContext
    from app.services.recommendation_sources_extra import LessonsLearnedSource, KnowledgeEntrySource
    from tests.capa.test_d5_consumers import qualify_test_vector_namespace
    case = controlled_root
    vector = [1.0] + [0.0] * 1535
    class Embedding:
        async def embed(self, texts):
            return [vector for _ in texts]
    async with case.session() as db:
        qualify_test_vector_namespace(db, monkeypatch)
        lesson_id, entry_id = uuid4(), uuid4()
        db.add(CapaLessonLearned(lesson_id=lesson_id, capa_id=case.report_id, factory_id=case.factory_id,
            product_line_code=case.line, lesson_text='old restricted lesson', lesson_text_normalized='old lesson',
            category='d7', source_d_step='d7'))
        db.add(KnowledgeEntry(entry_id=entry_id, source_type='capa', source_id=case.report_id,
            factory_id=case.factory_id, product_line_code=case.line, document_no='OLD-R6-KB', title='Old copy',
            fields={'lesson_summary': 'old restricted summary'}, embedding_text='old restricted root',
            content_hash='a' * 64, embedding_status='ready'))
        await db.flush()
        for kind, entity_id, field in [('capa_lesson', lesson_id, 'lesson_text'),
                                      ('knowledge_entry', entry_id, 'embedding_text')]:
            await db.execute(text("""INSERT INTO document_embeddings
                (id,entity_type,entity_id,entity_field,chunk_text,embedding,embedding_model,factory_id,product_line_code)
                VALUES (:id,:kind,:entity,:field,'old source copy',CAST(:vec AS vector),'fixture',:fid,:line)"""),
                dict(id=uuid4(), kind=kind, entity=entity_id, field=field, vec=str(vector), fid=case.factory_id, line=case.line))
        await db.commit()
        context = RecommendationContext({'product_line_code': case.line, 'd2_description': 'problem'},
            [case.line], 'd4', factory_id=case.factory_id)
        assert await LessonsLearnedSource(db, Embedding()).retrieve(context) == []
        assert await KnowledgeEntrySource(db, Embedding()).retrieve(context) == []
        from app.services.embedding_sync_worker import fetch_chunks
        assert await fetch_chunks(db, [dict(entity_type='capa_lesson', entity_id=lesson_id),
                                       dict(entity_type='knowledge_entry', entity_id=entry_id)]) == []


@pytest.mark.asyncio
async def test_null_capture_epoch_preserves_history_but_never_fresh_delivery(controlled_root):
    from app.services.capa_d4_material import read_root, require_root_freshness
    case = controlled_root
    async with case.session() as db:
        assert await read_root(db, case.actor('edit').user_id, case.report_id) == 'R6 protected root sentinel'
        with pytest.raises(PermissionError, match='D4_MATERIAL_STALE'):
            await require_root_freshness(db, case.actor('edit').user_id, case.report_id)


@pytest.mark.asyncio
async def test_capture_epoch_zero_is_valid_and_source_fenced(r6_case):
    from sqlalchemy import select
    from app.models.capa import CAPAEightD
    from app.services.capa_d4_material import capture_fmea_origin, require_root_freshness
    from app.services.capa_d4_provenance import record_root_revision
    case = r6_case
    async with case.session() as db:
        await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == case.report_id).with_for_update())
        source = await capture_fmea_origin(db, case.actor('edit').user_id, case.report_id, case.source_a.fmea_id, 'cause')
        assert type(source.source_version_counter) is int and source.source_version_counter == 0
        await record_root_revision(db, report_id=case.report_id, actor_id=case.actor('edit').user_id,
            write_path='r6:test-zero-epoch', added_source_ids=[source.source_id])
        await db.commit()
        _, sources = await require_root_freshness(db, case.actor('edit').user_id, case.report_id)
        assert sources[0].source_version_counter == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('outlet', ['pipeline', 'orchestrator', 'fusion', 'ppt'])
async def test_legacy_provider_result_never_returns_after_same_body_acquires_origins(r6_case, monkeypatch, outlet):
    from app.models.capa import CAPAEightD
    from app.models.agent_review_skill import AgentReviewSkill
    from app.services.agent import provider_adapter
    from app.services.recommendation_types import RecommendationContext
    case = r6_case
    actor = case.actor('edit')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.d1_team = [{'name': 'Owner', 'role': 'owner'}]
        report.d2_description, report.d3_interim = 'problem', 'containment'
        report.d4_root_cause = 'R6 protected root sentinel'
        report.d5_correction, report.d6_verification = 'correction', 'verification'
        report.d7_prevention, report.d8_closure = 'prevention', 'closure'
        report.fmea_node_id = 'cause'
        db.add(AgentReviewSkill(name='capa_ppt_review', tenant_schema=case.binding.schema_name,
            content='Review complete content', is_active=True))
        await db.commit()
    prompts = []
    async def receive(pc, prompt, schema):
        prompts.append(prompt)
        await bind_controlled_root(case)
        if outlet == 'ppt':
            return {'passed': True, 'issues': [], 'suggestions': []}
        return [{'content': 'derived confidential result', 'confidence': .8, 'match_reason': 'evidence'}]
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    context = RecommendationContext({'report_id': case.report_id, 'd4_root_cause': 'R6 protected root sentinel',
        'product_line_code': case.line, 'd2_description': 'problem'}, [case.line], 'd5', factory_id=case.factory_id)
    async with case.session() as db:
        with pytest.raises(PermissionError, match='D4'):
            if outlet == 'ppt':
                from app.services.capa_ppt_review_service import review_and_correct
                await review_and_correct(db, case.report_id, SimpleNamespace(model='receiver'),
                    case.binding.schema_name, scope=SimpleNamespace(user=actor))
            elif outlet == 'fusion':
                from app.services.llm_fusion_layer import LLMFusionLayer
                layer = LLMFusionLayer(SimpleNamespace(model='receiver'), db=db)
                await layer.enrich([], context)
            else:
                from app.services.recommendation_orchestrator import RecommendationOrchestrator
                from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
                cls = RecommendationOrchestrator if outlet == 'orchestrator' else HybridRecommendationPipeline
                service = cls(db, SimpleNamespace(model='receiver'), None)
                method = service.run if outlet == 'orchestrator' else service.recommend
                await method(context, user=actor, report_id=case.report_id,
                    factory_id=case.factory_id, tenant_schema=case.binding.schema_name)
    assert len(prompts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['d4', 'd5'])
async def test_legacy_recommendation_http_release_translates_revocation_to_denial(r6_case, monkeypatch, step):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    case = r6_case
    actor = case.actor('edit')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.d2_description, report.d4_root_cause = 'measurement problem', 'old unrestricted root'
        await db.commit()
    calls = []
    async def build(db):
        return SimpleNamespace(provider='openai', model='receiver', client=SimpleNamespace(base_url='https://receiver.invalid'))
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        await bind_controlled_root(case)
        return [{'content': 'derived private result', 'confidence': .8, 'match_reason': 'evidence'}]
    monkeypatch.setattr(app.state, 'embedding_provider', None, raising=False)
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url='http://test', headers=dict(actor.client.headers)) as client:
        response = await client.get(f'/api/capa/{case.report_id}/{step}-fmea-recommendations')
    assert response.status_code == 403, response.text
    assert 'items' not in response.json() and 'general_suggestions' not in response.json()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_embedding_inflight_result_does_not_recreate_controlled_copy(r6_case, monkeypatch):
    from sqlalchemy import text
    from app.models.capa import CAPAEightD
    from app.services.embedding_outbox import enqueue_embedding
    from app.services.embedding_sync_worker import process_batch_once
    from tests.capa.test_d5_consumers import qualify_test_vector_namespace
    case = r6_case
    calls = []
    class Receiver:
        model_name = 'controlled-test-embedding'
        async def embed(self, texts):
            calls.append(texts)
            assert 'R6 protected root sentinel' in str(texts)
            await bind_controlled_root(case)
            return [[1.0] + [0.0] * 1535 for _ in texts]
    async with case.session() as db:
        qualify_test_vector_namespace(db, monkeypatch)
        report = await db.get(CAPAEightD, case.report_id)
        report.d4_root_cause = 'R6 protected root sentinel'
        await enqueue_embedding(db, 'capa', case.report_id, case.line, case.factory_id)
        await db.commit()
        assert await process_batch_once(db, Receiver())
        assert await db.scalar(text("SELECT count(*) FROM document_embeddings WHERE entity_type='capa' AND entity_id=:id"),
            {'id': case.report_id}) == 0
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_direct_knowledge_bookmarks_hide_controlled_copies_before_payload_select(controlled_root):
    from sqlalchemy import event
    from app.models.knowledge_entry import KnowledgeEntry
    case = controlled_root
    entry_id = uuid4()
    async with case.session() as db:
        db.add(KnowledgeEntry(entry_id=entry_id, source_type='capa', source_id=case.report_id,
            factory_id=case.factory_id, product_line_code=case.line, document_no='R6-PRIVATE-COPY',
            title='R6 private copy', fields={'lesson_summary': 'root copy private sentinel'},
            embedding_text='root copy private sentinel', content_hash='a' * 64, embedding_status='ready'))
        await db.commit()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(case.runtime.engine.sync_engine, 'before_cursor_execute', capture)
    try:
        for mode in ('edit', 'view'):
            actor = case.actor(mode)
            if mode == 'view':
                await actor.revoke('fmea')
            for suffix in ('?source_type=capa', '?q=root%20copy%20private', f'/{entry_id}'):
                result = await actor.client.get('/api/knowledge/entries' + suffix)
                if suffix.startswith('/'):
                    assert result.status_code == 404, result.text
                else:
                    assert result.status_code == 200 and result.json()['total'] == 0, result.text
                    assert result.json()['items'] == []
                assert 'private sentinel' not in result.text
                assert result.headers.get('cache-control') == 'no-store'
    finally:
        event.remove(case.runtime.engine.sync_engine, 'before_cursor_execute', capture)
    assert not any('from knowledge_entries' in sql and
        ('knowledge_entries.fields' in sql.split('from knowledge_entries')[0]
         or 'knowledge_entries.embedding_text' in sql.split('from knowledge_entries')[0]) for sql in statements)


@pytest.mark.asyncio
async def test_rag_answer_and_sources_do_not_return_after_root_becomes_controlled(r6_case, monkeypatch):
    from sqlalchemy import text
    from app.models.capa import CAPAEightD
    from app.models.user import User
    from app.services.search_service import SearchService
    from app.services.agent import provider_adapter
    from tests.capa.test_d5_consumers import qualify_test_vector_namespace
    case = r6_case
    vector = [1.0] + [0.0] * 1535
    calls = []
    class Embedding:
        async def embed(self, texts):
            return [vector for _ in texts]
    async def build(db):
        return SimpleNamespace(provider='openai', model='receiver')
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        await bind_controlled_root(case)
        return {'answer': 'derived private answer'}
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    async with case.session() as db:
        qualify_test_vector_namespace(db, monkeypatch)
        report = await db.get(CAPAEightD, case.report_id)
        report.d4_root_cause = 'R6 protected root sentinel'
        await db.execute(text("""INSERT INTO document_embeddings
            (id,entity_type,entity_id,entity_field,chunk_text,embedding,embedding_model,factory_id,product_line_code)
            VALUES (:id,'capa',:rid,'d4_root_cause','R6 protected root sentinel',CAST(:vec AS vector),'fixture',:fid,:line)"""),
            dict(id=uuid4(), rid=case.report_id, vec=str(vector), fid=case.factory_id, line=case.line))
        await db.commit()
        user = await db.get(User, case.actor('edit').user_id)
        with pytest.raises(PermissionError, match='D4'):
            await SearchService(db, Embedding()).ask('root', user, case.binding.schema_name)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_lesson_extraction_never_publishes_ordinary_controlled_copy(controlled_root):
    from app.models.capa import CAPAEightD
    from app.services.capa_lessons_service import _extract_lessons
    async with controlled_root.session() as db:
        report = await db.get(CAPAEightD, controlled_root.report_id)
        with pytest.raises(PermissionError, match='D4'):
            await _extract_lessons(db, report, 'd7')


@pytest.mark.asyncio
@pytest.mark.parametrize('outlet', ['sink', 'doc_gate'])
async def test_copy_provider_result_rejected_after_root_acquires_origin(r6_case, monkeypatch, outlet):
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    case = r6_case
    calls = []
    async def build(db):
        return SimpleNamespace(provider='openai', model='controlled-receiver')
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        await bind_controlled_root(case)
        return {'lesson_summary': 'derived confidential result', 'tags': ['quality', 'process', 'root'],
            'affected_docs': []}
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.d4_root_cause = 'R6 protected root sentinel'
        report.status = 'D8_GATE_PENDING'
        await db.commit()
        with pytest.raises(PermissionError, match='D4'):
            if outlet == 'sink':
                from app.services.knowledge_sink_service import sink_capa_on_close
                await sink_capa_on_close(db, report, case.actor('edit').user_id, manual=True)
            else:
                from app.services.capa_doc_gate_service import generate_impact_analysis
                await generate_impact_analysis(db, report, case.actor('edit').user_id)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_old_lateral_projection_never_reads_controlled_copy(controlled_root):
    from app.services.capa_lateral_diffusion_service import _build_projection
    async with controlled_root.session() as db:
        from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck
        db.add(CapaLateralDiffusionCheck(check_id=uuid4(), capa_id=controlled_root.report_id,
            factory_id=controlled_root.factory_id, source_product_line_code=controlled_root.line,
            similar_products=[{'suggestion_direction': 'private derived result'}], status='done', llm_status='done'))
        await db.commit()
        assert await _build_projection(db, controlled_root.report_id) is None


@pytest.mark.asyncio
async def test_lateral_provider_result_never_publishes_after_root_promotion(r6_case, monkeypatch):
    from app.models.capa import CAPAEightD
    from app.services import capa_lateral_diffusion_service as service
    case = r6_case
    calls = []
    async def match(db, snapshot):
        return [dict(product_line_code=case.line, product_type_code='R6TYPE',
            factory_id=str(case.factory_id), hit_criteria=['same-source'], evidence={})]
    async def build(db):
        return SimpleNamespace(model='controlled-receiver')
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        await bind_controlled_root(case)
        return {'items': [{'product_type_code': 'R6TYPE', 'suggestion_direction': 'derived private result'}]}
    monkeypatch.setattr(service, 'match_criteria', match)
    monkeypatch.setattr(service, 'build_client', build)
    monkeypatch.setattr(service, 'complete_json', receive)
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.d4_root_cause = 'R6 protected root sentinel'
        await db.commit()
        with pytest.raises(PermissionError, match='D4'):
            await service.run_lateral_diffusion_check(db, report, case.actor('edit').user_id)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_local_ppt_export_uses_complete_current_root_authority(controlled_root, monkeypatch):
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    case = controlled_root
    async def unavailable(db):
        raise provider_adapter.ProviderNotConfiguredError('test has no model recipient')
    monkeypatch.setattr(provider_adapter, 'build_client', unavailable)
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D8_CLOSURE'
        report.d8_closure = 'Closed report content'
        await db.commit()
    actor = case.actor('edit')
    response = await actor.client.post(f'/api/capa/{case.report_id}/ppt-export')
    assert response.status_code == 200, response.text[:500]
    assert response.headers['cache-control'] == 'no-store'
    assert response.content.startswith(b'PK')
    await actor.revoke('fmea')
    denied = await actor.client.post(f'/api/capa/{case.report_id}/ppt-export')
    assert denied.status_code == 403 and not denied.content.startswith(b'PK'), denied.text


@pytest.mark.asyncio
@pytest.mark.parametrize('promotion', ['before', 'during'])
async def test_fusion_rechecks_historical_candidate_parent_after_provider(r6_case, monkeypatch, promotion):
    from app.models.capa import CAPAEightD
    from app.services.agent import provider_adapter
    from app.services.llm_fusion_layer import LLMFusionLayer
    from app.services.recommendation_types import RecommendationCandidate, RecommendationContext
    from app.services.capa_d4_material import legacy_recommendation_binding
    case = r6_case
    actor = case.actor('edit')
    target_id = uuid4()
    context = RecommendationContext({'report_id': target_id, 'd2_description': 'independent ordinary target'},
        [case.line], 'd4', factory_id=case.factory_id)
    async with case.session() as db:
        source = await db.get(CAPAEightD, case.report_id)
        source.d4_root_cause = 'R6 protected root sentinel'
        original_text = source.d4_root_cause
        db.add(CAPAEightD(report_id=target_id, document_no='R6-TARGET-' + target_id.hex[:8],
            title='Independent ordinary target', factory_id=case.factory_id,
            product_line_code=case.line, created_by=actor.user_id, status='D4_ROOT_CAUSE', d1_team=[]))
        await db.commit()
        context.actor_id = actor.user_id
        context.material_version = await legacy_recommendation_binding(db, actor, target_id)
    calls = []
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        await bind_controlled_root(case)
        return [{'content': 'generic model output without source metadata'}]
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    if promotion == 'before':
        await bind_controlled_root(case)
    candidate = RecommendationCandidate(source='historical_capa', content=original_text,
        category=None, confidence=.8, match_reason='historical evidence',
        metadata={'historical_capa_id': str(case.report_id)})
    async with case.session() as db:
        layer = LLMFusionLayer(SimpleNamespace(model='receiver'), db=db)
        # Fusion output may drop all provenance. The captured input set remains authoritative.
        monkeypatch.setattr(layer, '_merge_explanations', lambda candidates, result: [
            RecommendationCandidate(source='llm', content='generic private derived output', category=None,
                confidence=.8, match_reason='generated', metadata={}) for _ in range(3)])
        with pytest.raises(PermissionError, match='D4'):
            await layer.enrich([candidate], context)
        assert await legacy_recommendation_binding(db, actor, target_id) == context.material_version
    assert len(calls) == (0 if promotion == 'before' else 1)


@pytest.mark.asyncio
async def test_lessons_unbound_cache_is_metadata_only_miss_before_private_cards(r6_case, monkeypatch):
    from sqlalchemy import event, select, func, text
    from sqlalchemy.orm import selectinload
    from app.main import app
    from app.models.capa import CAPAEightD
    from app.models.user import User
    from app.models.recommendation_cache import RecommendationCache
    from app.services.lessons_learned.service import LessonsLearnedService
    case = r6_case
    target_id = uuid4()
    actor = case.actor('edit')
    async with case.session() as db:
        db.add(CAPAEightD(report_id=target_id, document_no='R6-CACHE-' + target_id.hex[:8],
            title='Independent ordinary cache target', factory_id=case.factory_id,
            product_line_code=case.line, created_by=actor.user_id, status='D4_ROOT_CAUSE',
            severity='general', d1_team=[]))
        await db.commit()
        user = await db.scalar(select(User).where(User.user_id == actor.user_id).options(selectinload(User.role_definition)))
        service = LessonsLearnedService(db, None)
        context = await service._build_context(target_id, 'capa', None, user)
        context_hash = service._compute_context_hash(context)
        db.add(RecommendationCache(factory_id=case.factory_id, product_line_code=case.line,
            trigger_type='lessons_learned', context_hash=context_hash, source='legacy generated summary',
            suggestions=[dict(id='old-card', title='private copied lesson', summary='private cache body sentinel',
                source_type='fmea', source_document_no='legacy', source_id=str(case.source_a.fmea_id),
                source_product_line=case.line, same_product_line=True, confidence=.8,
                match_reason='generated without original source metadata')],
            expires_at=func.now() + text("INTERVAL '1 hour'")))
        await db.commit()
    await bind_controlled_root(case)
    monkeypatch.setattr(app.state, 'embedding_provider', None, raising=False)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().lstrip().startswith('select') and 'recommendation_cache' in statement.lower():
            statements.append(statement.lower())
    event.listen(case.runtime.engine.sync_engine, 'before_cursor_execute', capture)
    try:
        response = await actor.client.post(f'/api/capa/{target_id}/lessons-learned', json={})
    finally:
        event.remove(case.runtime.engine.sync_engine, 'before_cursor_execute', capture)
    assert response.status_code == 200, response.text
    assert 'private cache body sentinel' not in response.text and response.json()['cached'] is False
    current = await actor.client.post(f'/api/capa/{target_id}/lessons-learned', json={})
    assert current.status_code == 200 and current.json()['cached'] is True, current.text
    assert not any('recommendation_cache.suggestions' in sql.split('from recommendation_cache')[0]
        and '->' not in sql.split('from recommendation_cache')[0] for sql in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['promotion', 'swap'])
async def test_trusted_cache_rechecks_original_parents_and_freezes_header(r6_case, monkeypatch, change):
    from sqlalchemy import select, update, func, text
    from app.models.capa import CAPAEightD
    from app.models.recommendation_cache import RecommendationCache
    from app.services.capa_d4_material import capture_legacy_candidate_bindings
    from app.services.capa_legacy_cache import seal_cache, load_cache
    from app.services.recommendation_types import RecommendationCandidate
    case = r6_case
    actor = case.actor('edit')
    cache_id, ordinary_id = uuid4(), uuid4()
    key = dict(kind='test-current-lineage', context_hash=cache_id.hex)
    def candidate(report_id):
        return RecommendationCandidate(source='historical_capa', content='ordinary admitted source',
            category=None, confidence=.8, match_reason='evidence', metadata={'historical_capa_id': str(report_id)})
    async with case.session() as db:
        db.add(CAPAEightD(report_id=ordinary_id, document_no='R6-CACHE-PARENT-' + ordinary_id.hex[:8],
            title='Ordinary independent cache parent', factory_id=case.factory_id, product_line_code=case.line,
            created_by=actor.user_id, status='D4_ROOT_CAUSE', d1_team=[]))
        await db.commit()
        protected_bindings = await capture_legacy_candidate_bindings(db, [candidate(case.report_id)], actor=actor)
        ordinary_bindings = await capture_legacy_candidate_bindings(db, [candidate(ordinary_id)], actor=actor)
        protected = seal_cache(db, key, protected_bindings,
            [{'text': 'private swapped source sentinel'}], {'source': 'generated'})
        ordinary = seal_cache(db, key, ordinary_bindings,
            [{'text': 'ordinary authorized cache result'}], {'source': 'generated'})
        envelope = protected if change == 'promotion' else ordinary
        db.add(RecommendationCache(cache_id=cache_id, factory_id=case.factory_id,
            product_line_code=case.line, trigger_type='lessons_learned', context_hash=cache_id.hex,
            source='generated', suggestions=envelope, expires_at=func.now() + text("INTERVAL '1 hour'")))
        await db.commit()
        filters = (RecommendationCache.cache_id == cache_id,)
        healthy = await load_cache(db, key, filters, actor=actor)
        assert healthy is not None and healthy[1] == (protected_bindings if change == 'promotion' else ordinary_bindings)
    await bind_controlled_root(case)
    async with case.session() as db:
        execute = db.execute
        swapped = False
        async def replace_after_metadata(statement, *args, **kwargs):
            nonlocal swapped
            result = await execute(statement, *args, **kwargs)
            columns = getattr(statement, 'column_descriptions', ())
            if not swapped and any(column.get('name') == 'header' for column in columns):
                swapped = True
                async with case.session() as writer:
                    await writer.execute(update(RecommendationCache).where(RecommendationCache.cache_id == cache_id)
                        .values(suggestions=protected))
                    await writer.commit()
            return result
        selected_cards = []
        scalar = db.scalar
        async def inspect_payload(statement, *args, **kwargs):
            value = await scalar(statement, *args, **kwargs)
            if 'cards' in statement.compile().params.values():
                selected_cards.append(value)
            return value
        monkeypatch.setattr(db, 'scalar', inspect_payload)
        if change == 'swap':
            monkeypatch.setattr(db, 'execute', replace_after_metadata)
        assert await load_cache(db, key, filters, actor=actor) is None
        assert selected_cards == ([None] if change == 'swap' else [])
        if change == 'swap':
            assert swapped


@pytest.mark.asyncio
async def test_indirect_fmea_recommendation_cache_cannot_launder_old_capa_copy(r6_case, monkeypatch):
    from sqlalchemy import update, func, text
    from app.main import app
    from app.models.role import RolePermission
    from app.models.recommendation_cache import RecommendationCache
    from app.services.agent import provider_adapter
    from app.services.recommendation_service import RecommendationService
    case = r6_case
    actor = case.actor('edit')
    payload = dict(trigger_type='failure_mode', context={'function_description': 'locating pin process'},
        scope='current_product_line', include_graph=False)
    context_hash = RecommendationService._compute_context_hash(None,
        payload['context'] | {'scope': payload['scope'], 'include_graph': False})
    async with case.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == actor.role_id,
            RolePermission.module == 'fmea').values(permission_level=3))
        db.add(RecommendationCache(fmea_id=case.source_a.fmea_id, factory_id=case.factory_id,
            product_line_code=case.line, trigger_type=payload['trigger_type'], context_hash=context_hash,
            source='hybrid', llm_available=False,
            suggestions=[dict(name='private indirect cache sentinel', confidence=.8, source='llm')],
            expires_at=func.now() + text("INTERVAL '1 hour'")))
        await db.commit()
    await bind_controlled_root(case)
    async def unavailable(db):
        raise provider_adapter.ProviderNotConfiguredError('deterministic no-model test')
    monkeypatch.setattr(provider_adapter, 'build_client', unavailable)
    monkeypatch.setattr(app.state, 'embedding_provider', None, raising=False)
    response = await actor.client.post(f'/api/fmea/{case.source_a.fmea_id}/recommend', json=payload)
    assert response.status_code == 200, response.text
    assert 'private indirect cache sentinel' not in response.text and response.json()['cached'] is False
    current = await actor.client.post(f'/api/fmea/{case.source_a.fmea_id}/recommend', json=payload)
    assert current.status_code == 200 and current.json()['cached'] is True, current.text
    await actor.revoke('capa')
    fmea_only = await actor.client.post(f'/api/fmea/{case.source_a.fmea_id}/recommend', json=payload)
    assert fmea_only.status_code == 200, fmea_only.text
    assert 'private indirect cache sentinel' not in fmea_only.text


@pytest.mark.asyncio
async def test_indirect_fmea_provider_retains_recalled_capa_parent_after_metadata_loss(r6_case, monkeypatch):
    from sqlalchemy import select, update, text
    from sqlalchemy.orm import selectinload
    from app.models.capa import CAPAEightD
    from app.models.user import User
    from app.models.role import RolePermission
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from app.schemas.recommendation import RecommendRequest
    from app.services.agent import provider_adapter
    from app.services.recommendation_service import RecommendationService
    from tests.capa.test_d5_consumers import qualify_test_vector_namespace
    case = r6_case
    actor = case.actor('edit')
    vector = [1.0] + [0.0] * 1535
    calls = []
    class Embedding:
        async def embed(self, texts):
            return [vector for _ in texts]
    async def build(db):
        return SimpleNamespace(provider='openai', model='controlled-receiver')
    async def receive(pc, prompt, schema):
        calls.append(prompt)
        await bind_controlled_root(case)
        return {'suggestions': [{'name': 'generic derived output without source metadata',
            'confidence': .8, 'explanation': 'generated'}]}
    monkeypatch.setattr(provider_adapter, 'build_client', build)
    monkeypatch.setattr(provider_adapter, 'complete_json', receive)
    async with case.session() as db:
        qualify_test_vector_namespace(db, monkeypatch)
        report = await db.get(CAPAEightD, case.report_id)
        report.d4_root_cause = 'R6 protected root sentinel'
        report.status = 'D8_CLOSURE'
        await db.execute(update(RolePermission).where(RolePermission.role_id == actor.role_id,
            RolePermission.module == 'fmea').values(permission_level=3))
        await db.execute(text("""INSERT INTO document_embeddings
            (id,entity_type,entity_id,entity_field,chunk_text,embedding,embedding_model,factory_id,product_line_code)
            VALUES (:id,'capa',:rid,'d2_description','ordinary admitted historical problem',
                CAST(:vec AS public.vector),'fixture',:fid,:line)"""),
            dict(id=uuid4(), rid=case.report_id, vec=str(vector), fid=case.factory_id, line=case.line))
        await db.commit()
        user = await db.scalar(select(User).where(User.user_id == actor.user_id).options(selectinload(User.role_definition)))
        scope = RequestScope(FactoryScope([case.factory_id], case.factory_id), case.factory_id,
            ProductLineScope('EXPLICIT', [case.line]), user)
        service = RecommendationService(db, SimpleNamespace(), embedding=Embedding())
        request = RecommendRequest(trigger_type='measure', context={'failure_mode': 'unclassified unusual process issue'},
            scope='current_product_line', include_graph=False)
        with pytest.raises(PermissionError, match='D4'):
            await service.recommend(case.source_a.fmea_id, request, user, scope, case.binding.schema_name)
        assert {item[0] for item in service._release_bindings} == {str(case.report_id)}
    assert len(calls) == 1


@pytest.mark.parametrize('command,body', [
    ('confirm', {'operation_key': 'confirm', 'expected_material_version': 'v', 'expected_candidate_version': 'v',
        'final_text': 'private canary\x00'}),
    ('correct', {'operation_key': 'correct', 'expected_material_version': 'v', 'expected_measure_version': 'v',
        'final_text': 'private canary\x00', 'reason': 'changed basis'}),
    ('candidate', {'command_key': 'candidate', 'text': 'safe proposal', 'supporting': ['private canary\x00']}),
    ('proposal', {'command_key': 'proposal', 'text': 'private canary\x00'}),
    ('adopt', {'operation_key': 'adopt', 'final_text': 'private canary\x00'}),
])
def test_r6_material_commands_reject_database_invalid_nul(command, body):
    from pydantic import ValidationError
    from app.schemas.capa_r6 import D4Confirm, D5Correct, D4CandidateCommand
    from app.schemas.agent_d5_command import D5Command
    from app.schemas.capa_d5_staff import D5Adopt
    schemas = dict(confirm=D4Confirm, correct=D5Correct, candidate=D4CandidateCommand,
        proposal=D5Command, adopt=D5Adopt)
    with pytest.raises(ValidationError):
        schemas[command].model_validate(body)


def test_shared_business_database_engine_hides_bound_parameters():
    from app.database import engine, tenant_async_session, async_session
    assert engine.sync_engine.hide_parameters is True
    assert tenant_async_session.kw['bind'].sync_engine.hide_parameters is True
    assert async_session.kw['bind'].sync_engine.hide_parameters is True


@pytest.mark.asyncio
async def test_normal_protected_manual_put_rejects_nul_without_material_write(controlled_root):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    case = controlled_root
    actor = case.actor('edit')
    current = await actor.client.get(f'/api/capa/{case.report_id}')
    assert current.status_code == 200, current.text
    token = current.json()['material_version']
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url='http://test', headers=dict(actor.client.headers)) as client:
        response = await client.put(f'/api/capa/{case.report_id}', json=dict(
            expected_material_version=token, d4_root_cause='private invalid write canary\x00'))
    assert response.status_code == 422, response.text
    after = await actor.client.get(f'/api/capa/{case.report_id}')
    assert after.status_code == 200 and after.json()['material_version'] == token, after.text
    assert after.json()['d4_root_cause'] == current.json()['d4_root_cause']


def test_manual_capa_text_stays_unbounded_and_json_nul_is_rejected():
    from pydantic import ValidationError
    from app.schemas.capa import CAPAUpdate
    large = 'complete manual text ' * 4096 + r' literal \u0000 stays text'
    assert CAPAUpdate(d4_root_cause=large).d4_root_cause == large
    with pytest.raises(ValidationError):
        CAPAUpdate(d1_team=[{'member': {'name': 'invalid\x00'}}])


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['control', 'actor'])
async def test_scar_waiter_rechecks_before_loading_body_and_creating_copy(r6_case, change):
    import asyncio
    from sqlalchemy import select, event, func
    from sqlalchemy.engine import Engine
    from app.models.capa import CAPAEightD
    from app.models.supplier import Supplier
    from app.models.supplier import SupplierSCAR
    from app.services.capa_d4_material import capture_fmea_origin
    from app.services.capa_d4_provenance import record_root_revision
    case = r6_case
    actor = case.actor('edit')
    supplier_id = uuid4()
    async with case.session() as db:
        db.add(Supplier(supplier_id=supplier_id, supplier_no='R6-SCAR-' + supplier_id.hex[:8],
            name='Owned source supplier', short_name='Owned', factory_id=case.factory_id, created_by=actor.user_id))
        report = await db.get(CAPAEightD, case.report_id)
        report.status = 'D4_ROOT_CAUSE'
        report.d4_root_cause = 'ordinary initial root'
        await db.commit()
    waiting = asyncio.Event()
    statements = []
    async with case.session() as locker:
        await locker.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == case.report_id).with_for_update())
        owned_connection = (await locker.connection()).sync_connection
        def capture(conn, cursor, statement, parameters, context, executemany):
            if conn is owned_connection:
                return
            sql = statement.lower()
            statements.append(sql)
            if 'from capa_eightd' in sql and 'for update' in sql:
                waiting.set()
        event.listen(Engine, 'before_cursor_execute', capture)
        pending = asyncio.create_task(actor.client.post(f'/api/capa/{case.report_id}/trigger-scar',
            json={'supplier_id': str(supplier_id)}))
        try:
            await asyncio.wait_for(waiting.wait(), 5)
            if change == 'control':
                report = await locker.get(CAPAEightD, case.report_id)
                report.d4_root_cause = 'R6 protected root sentinel'
                origin = await capture_fmea_origin(locker, actor.user_id, case.report_id, case.source_a.fmea_id, 'cause')
                await record_root_revision(locker, report_id=case.report_id, actor_id=actor.user_id,
                    write_path='r6:test-scar-waiter', added_source_ids=[origin.source_id])
            else:
                await actor.revoke('edit')
            await locker.commit()
            response = await asyncio.wait_for(pending, 10)
        finally:
            event.remove(Engine, 'before_cursor_execute', capture)
    assert response.status_code == 403, response.text
    assert not any('for update' in sql and 'capa_eightd.d4_root_cause' in sql.split('from capa_eightd')[0]
        for sql in statements)
    async with case.session() as db:
        assert await db.scalar(select(func.count()).select_from(SupplierSCAR).where(SupplierSCAR.capa_ref_id == case.report_id)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_error', ['server', 'redirect', 'ollama', 'server_no_promotion'])
async def test_embedding_physical_requests_and_error_records_stop_after_source_promotion(r6_case, monkeypatch, caplog, provider_error):
    import logging
    import json
    import httpx
    from openai import AsyncOpenAI
    from sqlalchemy import select, func
    from app.models.capa import CAPAEightD
    from app.models.document_embedding import EmbeddingSyncOutbox, DocumentEmbedding
    from app.services.embedding_outbox import enqueue_embedding
    from app.services.embedding_sync_worker import process_batch_once
    from app.services.embedding_provider import OpenAIEmbeddingProvider, OllamaEmbeddingProvider
    case = r6_case
    canary = 'R6_PRIVATE_EMBEDDING_CANARY'
    bodies, urls = [], []
    async def receive(request):
        bodies.append(request.content)
        urls.append(str(request.url))
        if len(bodies) == 1:
            assert canary.encode() in request.content
            if provider_error != 'server_no_promotion':
                await bind_controlled_root(case)
        if provider_error == 'ollama':
            return httpx.Response(200, json={'embedding': [1.0] + [0.0] * 1535})
        if provider_error == 'redirect':
            if request.url.host == 'other-recipient.invalid':
                payload = json.loads(request.content)
                return httpx.Response(200, json={'data': [{'embedding': [1.0] + [0.0] * 1535, 'index': index}
                    for index, _ in enumerate(payload['input'])]})
            return httpx.Response(307, headers={'Location': 'https://other-recipient.invalid/steal'}, text=canary)
        return httpx.Response(503, json={'error': {'message': canary}})
    transport = httpx.AsyncClient(transport=httpx.MockTransport(receive), follow_redirects=True)
    if provider_error == 'ollama':
        provider = OllamaEmbeddingProvider(base_url='https://receiver.invalid', dimensions=1536)
        await provider._client.aclose()
        provider._client = transport
    else:
        provider = OpenAIEmbeddingProvider(api_key='owned-synthetic-test-key', base_url='https://receiver.invalid/v1')
        await provider._client.close()
        provider._client = AsyncOpenAI(api_key='owned-synthetic-test-key', base_url='https://receiver.invalid/v1',
            http_client=transport, max_retries=2)
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.DEBUG, logger='openai._base_client')
    async with case.session() as db:
        report = await db.get(CAPAEightD, case.report_id)
        report.d2_description = report.d4_root_cause = canary
        await enqueue_embedding(db, 'capa', case.report_id, case.line, case.factory_id)
        await db.commit()
        try:
            events = await process_batch_once(db, provider)
        finally:
            await provider.aclose()
        assert len(bodies) == 1 and all('other-recipient.invalid' not in url for url in urls)
        if provider_error == 'server_no_promotion':
            assert events is None
        else:
            assert events
        assert await db.scalar(select(func.count()).select_from(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == 'capa', DocumentEmbedding.entity_id == case.report_id)) == 0
        errors = list(await db.scalars(select(EmbeddingSyncOutbox.last_error).where(EmbeddingSyncOutbox.entity_id == case.report_id)))
        assert all(canary not in str(error) for error in errors)
        statuses = list(await db.scalars(select(EmbeddingSyncOutbox.status).where(EmbeddingSyncOutbox.entity_id == case.report_id)))
        assert ('pending' if provider_error == 'server_no_promotion' else 'cancelled') in statuses
    assert canary not in caplog.text
