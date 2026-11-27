import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import D5MeasureCorrection from './D5MeasureCorrection';
import * as api from '../../api/capaR6';
vi.mock('../../api/capaR6',()=>({getMeasure:vi.fn(),getMeasureHistory:vi.fn(),correctD5:vi.fn(),getSourceDetails:vi.fn()}));
const measure={measure_id:'a',proposal_id:'p',final_text:'当前正式措施',adopted_text:'初次采纳',adopted_by:'员工',adopted_at:'2026-11-16',current_version:'v1',material_version:'complete-m1',can_correct:true,correction_revision_id:null,correction_revision_no:0};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(api.getMeasure).mockResolvedValue(measure);vi.mocked(api.getMeasureHistory).mockResolvedValue({...measure,corrections:[]});});afterEach(cleanup);
it('provides selected-item correction with full-body-independent expected versions',async()=>{
 render(<D5MeasureCorrection capaId="report" measureId="a"/>);
 fireEvent.change(await screen.findByLabelText('更正后全文'),{target:{value:'员工更正措施'}});
 fireEvent.change(screen.getByLabelText('更正理由'),{target:{value:'明确措辞'}});
 fireEvent.click(screen.getByRole('button',{name:'提交更正'}));
 await waitFor(()=>expect(api.correctD5).toHaveBeenCalledWith('report','a',{operation_key:expect.any(String),expected_material_version:'complete-m1',expected_measure_version:'v1',final_text:'员工更正措施',reason:'明确措辞'},expect.any(AbortSignal)));
});
it('displays adoption and immutable correction history; VIEW has no correction action',async()=>{
 vi.mocked(api.getMeasure).mockResolvedValue({...measure,can_correct:false});
 vi.mocked(api.getMeasureHistory).mockResolvedValue({...measure,corrections:[{revision_id:'r',revision_no:1,final_text:'历史更正',reason:'历史理由',actor_id:'员工2',created_at:'2026-11-16'}]});
 render(<D5MeasureCorrection capaId="report" measureId="a"/>);await screen.findByText('历史更正');
 expect(screen.getByText('初次采纳')).toBeInTheDocument();expect(screen.queryByRole('button',{name:'提交更正'})).toBeNull();
});
it('clears edited body and history when 403 occurs',async()=>{
 vi.mocked(api.correctD5).mockRejectedValue({response:{status:403}});
 render(<D5MeasureCorrection capaId="report" measureId="a"/>);
 fireEvent.change(await screen.findByLabelText('更正后全文'),{target:{value:'受限编辑'}});
 fireEvent.change(screen.getByLabelText('更正理由'),{target:{value:'理由'}});
 vi.mocked(api.getMeasure).mockRejectedValue({response:{status:403}});
 fireEvent.click(screen.getByRole('button',{name:'提交更正'}));
 await waitFor(()=>expect(screen.queryByDisplayValue('受限编辑')).toBeNull());expect(screen.queryByText('初次采纳')).toBeNull();
});

it('clears an unsaved correction when polling observes a different complete material version',async()=>{
 render(<D5MeasureCorrection capaId="report" measureId="a"/>);
 fireEvent.change(await screen.findByLabelText('更正后全文'),{target:{value:'旧材料草稿'}});
 vi.mocked(api.getMeasure).mockResolvedValue({...measure,material_version:'complete-m2'});
 await waitFor(()=>expect(screen.queryByDisplayValue('旧材料草稿')).toBeNull(),{timeout:3000});
});
