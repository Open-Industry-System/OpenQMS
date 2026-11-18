import {render,screen,fireEvent,waitFor,cleanup,act} from '@testing-library/react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import D4CandidatePanel from './D4CandidatePanel';
import * as api from '../../api/capaR6';
vi.mock('../../api/capaR6',()=>({listD4Candidates:vi.fn(),getD4Confirmation:vi.fn(),confirmD4:vi.fn(),withdrawD4:vi.fn(),getSourceDetails:vi.fn()}));
const candidate={candidate_id:'candidate',state:'pending' as const,version:'v1',material_version:'m1',original_text:'候选原文',supporting:['证据'],opposing:[],missing_information:['缺少复测'],can_confirm:true,can_withdraw:true};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(api.listD4Candidates).mockResolvedValue({items:[candidate],page:1,page_size:20});vi.mocked(api.getD4Confirmation).mockResolvedValue({candidate_id:'candidate',current_root_text:'原正式根因',material_version:'m1',candidate_version:'v1',can_confirm:true});});
afterEach(cleanup);
it('confirms edited append with expected versions independently of verification',async()=>{
 render(<D4CandidatePanel capaId="report"/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对并确认 candidate'}));
 fireEvent.change(await screen.findByLabelText('最终根因'),{target:{value:'员工修改根因'}});
 fireEvent.click(screen.getByRole('button',{name:'确认正式根因'}));
 await waitFor(()=>expect(api.confirmD4).toHaveBeenCalledWith('report','candidate',{operation_key:expect.any(String),expected_material_version:'m1',expected_candidate_version:'v1',mode:'append',final_text:'员工修改根因'},expect.any(AbortSignal)));
 expect(screen.queryByText('验证通过')).toBeNull();
});
it('requires explicit replace comparison confirmation',async()=>{
 render(<D4CandidatePanel capaId="report"/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对并确认 candidate'}));
 await screen.findByLabelText('最终根因');
 fireEvent.change(screen.getByLabelText('写入方式'),{target:{value:'replace'}});
 expect(screen.getByText('原正式根因')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'确认正式根因'})).toBeDisabled();
 fireEvent.click(screen.getByLabelText('已核对全文替换差异'));
 expect(screen.getByRole('button',{name:'确认正式根因'})).toBeEnabled();
});
it('hides confirm/withdraw actions from VIEW',async()=>{
 vi.mocked(api.listD4Candidates).mockResolvedValue({items:[{...candidate,can_confirm:false,can_withdraw:false}],page:1,page_size:20});
 render(<D4CandidatePanel capaId="report"/>);await screen.findByText('候选原文');
 expect(screen.queryByRole('button',{name:'核对并确认 candidate'})).toBeNull();
 expect(screen.queryByRole('button',{name:'撤回 candidate'})).toBeNull();
});
it('retries the exact unknown-network request then clears drafts on 409',async()=>{
 vi.mocked(api.confirmD4).mockRejectedValueOnce(new Error('network')).mockRejectedValueOnce({response:{status:409}});
 render(<D4CandidatePanel capaId="report"/>);fireEvent.click(await screen.findByRole('button',{name:'核对并确认 candidate'}));
 fireEvent.change(await screen.findByLabelText('最终根因'),{target:{value:'旧编辑'}});
 fireEvent.click(screen.getByRole('button',{name:'确认正式根因'}));
 fireEvent.click(await screen.findByRole('button',{name:'重试原请求'}));
 await waitFor(()=>expect(api.confirmD4).toHaveBeenCalledTimes(2));
 expect(vi.mocked(api.confirmD4).mock.calls[0][2]).toEqual(vi.mocked(api.confirmD4).mock.calls[1][2]);
 await waitFor(()=>expect(screen.queryByDisplayValue('旧编辑')).toBeNull());
});
it('does not paint a late old report response',async()=>{
 let resolve!:(v:any)=>void;vi.mocked(api.listD4Candidates).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValue({items:[],page:1,page_size:20});
 const view=render(<D4CandidatePanel capaId="old"/>);view.rerender(<D4CandidatePanel capaId="new"/>);
 await act(async()=>resolve({items:[candidate],page:1,page_size:20}));expect(screen.queryByText('候选原文')).toBeNull();
});

it('treats an explicit request-size rejection as confirmed rejection and clears the old form',async()=>{
 vi.mocked(api.confirmD4).mockRejectedValue({response:{status:413}});
 render(<D4CandidatePanel capaId="report"/>);fireEvent.click(await screen.findByRole('button',{name:'核对并确认 candidate'}));
 fireEvent.change(await screen.findByLabelText('最终根因'),{target:{value:'rejected-draft'}});
 fireEvent.click(screen.getByRole('button',{name:'确认正式根因'}));
 await waitFor(()=>expect(screen.queryByDisplayValue('rejected-draft')).toBeNull());
 expect(screen.queryByRole('button',{name:'重试原请求'})).toBeNull();
});

it('keeps the latest selected candidate when a previous confirmation context arrives late',async()=>{
 const second={...candidate,candidate_id:'second',original_text:'第二候选',version:'v2',material_version:'m2'};
 vi.mocked(api.listD4Candidates).mockResolvedValue({items:[candidate,second],page:1,page_size:20});
 let resolve!:(v:api.D4Confirmation)=>void;
 vi.mocked(api.getD4Confirmation).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValueOnce({candidate_id:'second',current_root_text:'当前全文',material_version:'m2',candidate_version:'v2',can_confirm:true});
 render(<D4CandidatePanel capaId="report"/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对并确认 candidate'}));
 fireEvent.click(screen.getByRole('button',{name:'核对并确认 second'}));
 await screen.findByDisplayValue('第二候选');
 await act(async()=>resolve({candidate_id:'candidate',current_root_text:'旧全文',material_version:'m1',candidate_version:'v1',can_confirm:true}));
 expect(screen.getByLabelText('最终根因')).toHaveValue('第二候选');
 fireEvent.click(screen.getByRole('button',{name:'确认正式根因'}));
 await waitFor(()=>expect(api.confirmD4).toHaveBeenCalledWith('report','second',expect.objectContaining({expected_material_version:'m2',expected_candidate_version:'v2',final_text:'第二候选'}),expect.any(AbortSignal)));
});
