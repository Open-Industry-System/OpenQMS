# backend/tests/test_cp_sync_outbox_model.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.cp_sync_outbox import CPSyncOutbox


@pytest.mark.asyncio
async def test_model_persists_and_unique_event_key(db):
    fmea_id, version_id = uuid.uuid4(), uuid.uuid4()
    db.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id,
                        event_type="cp.sync_pending_set", payload={}))
    await db.commit()
    db.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id,
                        event_type="cp.sync_pending_set", payload={}))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    db.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=uuid.uuid4(),
                        event_type="cp.sync_pending_set", payload={}))
    await db.commit()
