import {beforeEach,expect,it,vi} from 'vitest';
import client from './client';
import {adoptD5Proposal,withdrawD5Proposal,listD5Proposals,withdrawCheckpointProposals} from './d5Proposals';
vi.mock('./client',()=>({default:{get:vi.fn(),post:vi.fn()}}));
const id='00000000-0000-4000-8000-000000000001';
beforeEach(()=>vi.clearAllMocks());
it('rejects a successful action response for another proposal or missing adoption receipt',async()=>{
  vi.mocked(client.post).mockResolvedValue({data:{proposal_id:'other',state:'adopted'}});
  await expect(adoptD5Proposal(id,id,{operation_key:'k',final_text:'final'})).rejects.toThrow();
  vi.mocked(client.post).mockResolvedValue({data:{proposal_id:id,state:'pending'}});
  await expect(withdrawD5Proposal(id,id,{operation_key:'k',reason:'why'})).rejects.toThrow();
});
it('rejects malformed server qualification and batch outcomes outside the requested set',async()=>{
  vi.mocked(client.get).mockResolvedValue({data:{items:[{proposal_id:id,task_id:id,state:'pending',original_text:'x',basis_current:true,created_at:'2026-11-14T00:00:00Z'}],total:1,page:1,page_size:20}});
  await expect(listD5Proposals(id)).rejects.toThrow();
  vi.mocked(client.post).mockResolvedValue({data:[{proposal_id:'other',outcome:'withdrawn'}]});
  await expect(withdrawCheckpointProposals(id,id,{operation_key:'k',reason:'why',proposal_ids:[id]})).rejects.toThrow();
});
it('requests a bounded current-task pending page and rejects mismatched selector rows',async()=>{
  const {listTaskD5Proposals}=await import('./d5Proposals');
  const signal=new AbortController().signal;
  vi.mocked(client.get).mockResolvedValueOnce({data:{items:[],total:0,page:2,page_size:20}});
  await listTaskD5Proposals(id,id,2,signal);
  expect(client.get).toHaveBeenLastCalledWith(`/capa/${id}/d5-proposals`,{params:{page:2,page_size:20,task_id:id,state:'pending'},signal});
  vi.mocked(client.get).mockResolvedValueOnce({data:{items:[{proposal_id:id,task_id:'other-task',original_text:'readable other task',state:'pending',basis_current:true,can_adopt:true,can_withdraw:true,created_at:'2026-11-14T00:00:00Z'}],total:1,page:1,page_size:20}});
  await expect(listTaskD5Proposals(id,id)).rejects.toThrow('Invalid correction task page');
});
