"""Real commits and exceptional fixture exits cannot pollute another case."""
import os

import pytest
from sqlalchemy import select, update

from app.core.tenant_utils import slug_to_schema_name
from app.models.capa import CAPAEightD
from app.models.user import User
from tests.ci.owned_resources import _connect
from tests.e2e.agent_local_trial_harness import MARKER
from tests.services.agent_runtime.d4_fixture_support import prepared_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


async def test_committed_mutation_and_failed_case_leave_next_runtime_clean(
        runtime_tenant_template, tmp_path):
    template, _ = runtime_tenant_template
    databases = []
    for index in range(2):
        path = tmp_path / str(index)
        path.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            fixture = prepared_local_trial.__wrapped__(runtime_tenant_template, patch, path)
            try:
                case = await anext(fixture)
                assert case.binding.schema_name == slug_to_schema_name(case.slug)
                databases.append(os.environ['TEST_DATABASE_URL'])
                async with case.session() as db:
                    assert (await db.get(User, case.user_id)).is_active
                    assert (await db.get(CAPAEightD, case.report_id)).d4_root_cause == MARKER
                    if index == 0:
                        await db.execute(update(User).where(User.user_id == case.user_id).values(is_active=False))
                        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == case.report_id)
                            .values(d4_root_cause='committed contamination sentinel'))
                        await db.commit()
                        assert not (await db.scalar(select(User).where(User.user_id == case.user_id))).is_active
                # Close the independent session before fixture teardown; its
                # new SELECT transaction must not hold the schema's read lock.
                if index == 0:
                    with pytest.raises(RuntimeError, match='case failure'):
                        await fixture.athrow(RuntimeError('case failure'))
            finally:
                await fixture.aclose()
    assert databases[0] != databases[1]
    from sqlalchemy.engine import make_url

    with _connect(template.admin_url) as connection:
        for url in databases:
            assert connection.execute('SELECT 1 FROM pg_database WHERE datname = %s',
                (make_url(url).database,)).fetchone() is None
