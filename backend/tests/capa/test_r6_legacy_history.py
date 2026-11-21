"""Old adoption identity stays an immutable historical fact."""
import pytest
from sqlalchemy import select,func
from app.models.capa import CapaAIAdoption
from app.models.capa_r6 import CapaD4Candidate
pytestmark=pytest.mark.requires_db

@pytest.mark.asyncio
async def test_old_adoption_keeps_real_identity_and_unattested_history(r6_case):
    c=r6_case
    async with c.session() as db:
        row=CapaAIAdoption(capa_id=c.report_id,factory_id=c.factory_id,d_step='d4',adopted_text='true old text',
            source='historical-source',item_ref={'legacy':'original-coordinate'},adopted_by=c.actor('second_edit').user_id)
        db.add(row)
        await db.commit()
        row_id=row.adoption_id
    before=await c.snapshot()
    response=await c.actor().client.get(f'/api/capa/{c.report_id}/legacy-adoptions')
    assert response.status_code==200,response.text
    item=response.json()['items'][0]
    assert item['adoption_id']==str(row_id)
    assert item['adopted_by']==str(c.actor('second_edit').user_id)
    assert item['source']=='historical-source' and item['item_ref']=={'legacy':'original-coordinate'}
    assert item['adopted_text']=='true old text' and item['source_status']=='historical_unattested'
    assert await c.snapshot()==before
    await c.actor().revoke('capa')
    assert (await c.actor().client.get(f'/api/capa/{c.report_id}/legacy-adoptions')).status_code in {403,404}
