import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import { beforeEach, afterEach, it, expect, vi } from 'vitest';
import D5ProposalPanel from './D5ProposalPanel';
import * as api from '../../api/d5Proposals';
vi.mock('../../api/d5Proposals',()=>({listD5Proposals:vi.fn(),listD5Measures:vi.fn(),adoptD5Proposal:vi.fn(),withdrawD5Proposal:vi.fn(),checkpointProposals:vi.fn(),withdrawCheckpointProposals:vi.fn()}));
const proposal={proposal_id:'p1',task_id:'ended-task',original_text:'Agent 原文',state:'pending' as const,basis_current:true,can_adopt:true,can_withdraw:true,created_at:'2026-11-14T00:00:00Z'};
beforeEach(()=>{
  vi.clearAllMocks();
  vi.mocked(api.listD5Measures).mockResolvedValue({legacy_text:null,items:[],total:0,page:1,page_size:20});
  vi.mocked(api.listD5Proposals).mockResolvedValue({items:[proposal],total:1,page:1,page_size:20});
});
afterEach(cleanup);
it('colleague edits final text and adopts report-owned proposal after task ended',async()=>{
  vi.mocked(api.adoptD5Proposal).mockResolvedValue({proposal_id:'p1',state:'adopted'});
  render(<D5ProposalPanel capaId="report" />);
  expect(await screen.findByText('Agent 原文',{selector:'p'})).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('最终措施 p1'),{target:{value:'员工确认措施'}});
  fireEvent.click(screen.getByRole('button',{name:'采纳 p1'}));
  await waitFor(()=>expect(api.adoptD5Proposal).toHaveBeenCalledWith('report','p1',{operation_key:expect.any(String),final_text:'员工确认措施'},expect.any(AbortSignal)));
});
it('uses server qualification and shows stale basis without allowing adoption',async()=>{
  vi.mocked(api.listD5Proposals).mockResolvedValue({items:[{...proposal,basis_current:false,can_adopt:false}],total:1,page:1,page_size:20});
  render(<D5ProposalPanel capaId="report" />);
  expect(await screen.findByText('依据过时')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'采纳 p1'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('撤回原因 p1'),{target:{value:'依据过时'}});
  expect(screen.getByRole('button',{name:'撤回 p1'})).toBeEnabled();
});
it('clears hidden original and edited bodies on conflict refresh',async()=>{
  vi.mocked(api.adoptD5Proposal).mockRejectedValue({response:{status:409}});
  render(<D5ProposalPanel capaId="report" />);
  await screen.findByText('Agent 原文',{selector:'p'});
  fireEvent.change(screen.getByLabelText('最终措施 p1'),{target:{value:'旧编辑文本'}});
  vi.mocked(api.listD5Proposals).mockResolvedValue({items:[],total:0,page:1,page_size:20});
  fireEvent.click(screen.getByRole('button',{name:'采纳 p1'}));
  await waitFor(()=>expect(screen.queryByText('Agent 原文',{selector:'p'})).toBeNull());
  expect(screen.queryByDisplayValue('旧编辑文本')).toBeNull();
});
it('ignores a late response after report changes',async()=>{
  let resolve!: (v:any)=>void;
  vi.mocked(api.listD5Proposals).mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValue({items:[],total:0,page:1,page_size:20});
  const view=render(<D5ProposalPanel capaId="old" />);
  view.rerender(<D5ProposalPanel capaId="new" />);
  await act(async()=>resolve({items:[proposal],total:1,page:1,page_size:20}));
  expect(screen.queryByText('Agent 原文',{selector:'p'})).toBeNull();
});
it('selects checkpoint items individually and shows every batch outcome',async()=>{
  vi.mocked(api.checkpointProposals).mockResolvedValue([{proposal_id:'p1',state:'pending',sequence:3}]);
  vi.mocked(api.withdrawCheckpointProposals).mockResolvedValue([{proposal_id:'p1',outcome:'withdrawn'}]);
  render(<D5ProposalPanel capaId="report" checkpoint={{taskId:'ended-task',checkpointId:'cp'}} />);
  fireEvent.click(await screen.findByLabelText('选择建议 p1'));
  fireEvent.change(screen.getByLabelText('批量撤回原因'),{target:{value:'纠正方向'}});
  fireEvent.click(screen.getByRole('button',{name:'撤回选中建议'}));
  await waitFor(()=>expect(api.withdrawCheckpointProposals).toHaveBeenCalledWith('ended-task','cp',expect.objectContaining({proposal_ids:['p1'],reason:'纠正方向'}),expect.any(AbortSignal)));
  expect(await screen.findByText('p1：withdrawn')).toBeInTheDocument();
});
it('clears original and unsaved final draft when current reader loses access',async()=>{
  render(<D5ProposalPanel capaId="report"/>);
  await screen.findByText('Agent 原文',{selector:'p'});
  fireEvent.change(screen.getByLabelText('最终措施 p1'),{target:{value:'受限草稿'}});
  vi.mocked(api.listD5Proposals).mockRejectedValue({response:{status:403}});
  fireEvent.click(screen.getByRole('button',{name:'刷新建议'}));
  await screen.findByText('建议不可用；已清除旧文本，请检查当前权限。');
  expect(screen.queryByText('Agent 原文',{selector:'p'})).toBeNull();
  expect(screen.queryByDisplayValue('受限草稿')).toBeNull();
});
it('retries an unconfirmed staff action with original key and text; blocks refresh during write',async()=>{
  let reject!:(e:unknown)=>void;
  vi.mocked(api.adoptD5Proposal).mockReturnValueOnce(new Promise((_,r)=>{reject=r})).mockResolvedValueOnce({proposal_id:'p1',state:'adopted'});
  render(<D5ProposalPanel capaId="report"/>);
  await screen.findByText('Agent 原文',{selector:'p'});
  fireEvent.change(screen.getByLabelText('最终措施 p1'),{target:{value:'原确认文本'}});
  fireEvent.click(screen.getByRole('button',{name:'采纳 p1'}));
  expect(screen.getByRole('button',{name:'刷新建议'})).toBeDisabled();
  await act(async()=>reject(new Error('unknown write')));
  fireEvent.click(await screen.findByRole('button',{name:'重试原处理'}));
  await waitFor(()=>expect(api.adoptD5Proposal).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.adoptD5Proposal).mock.calls[1][2]).toEqual(vi.mocked(api.adoptD5Proposal).mock.calls[0][2]);
});

it('reads formal final text and adopter after task-ended reload and clears it on revoke',async()=>{
  vi.mocked(api.listD5Proposals).mockResolvedValue({items:[{...proposal,state:'adopted',can_adopt:false,can_withdraw:false}],total:1,page:1,page_size:20});
  vi.mocked(api.listD5Measures).mockResolvedValue({legacy_text:null,items:[{measure_id:'m1',proposal_id:'p1',final_text:'服务端正式最终文本',adopted_by:'colleague-id',adopted_at:'2026-11-14T00:00:00Z'}],total:1,page:1,page_size:20});
  render(<D5ProposalPanel capaId="report"/>);
  expect(await screen.findByText('服务端正式最终文本')).toBeInTheDocument();
  expect(screen.getByText('Agent 原文',{selector:'p'})).toBeInTheDocument();
  expect(screen.getByText(/colleague-id/)).toBeInTheDocument();
  vi.mocked(api.listD5Measures).mockRejectedValue({response:{status:403}});
  fireEvent.click(screen.getByRole('button',{name:'刷新建议'}));
  await screen.findByText('建议不可用；已清除旧文本，请检查当前权限。');
  expect(screen.queryByText('服务端正式最终文本')).toBeNull();
});
it('purges an unknown write retry when a successful poll filters out its target',async()=>{
  vi.mocked(api.adoptD5Proposal).mockRejectedValue(new Error('lost response'));
  render(<D5ProposalPanel capaId="report"/>);
  await screen.findByText('Agent 原文',{selector:'p'});
  fireEvent.change(screen.getByLabelText('最终措施 p1'),{target:{value:'受限待确认正文'}});
  fireEvent.click(screen.getByRole('button',{name:'采纳 p1'}));
  await screen.findByRole('button',{name:'重试原处理'});
  vi.mocked(api.listD5Proposals).mockResolvedValue({items:[],total:0,page:1,page_size:20});
  await waitFor(()=>expect(screen.queryByRole('button',{name:'重试原处理'})).toBeNull(),{timeout:3000});
  expect(screen.queryByDisplayValue('受限待确认正文')).toBeNull();
});
it('paginates formal measures independently from proposal pages',async()=>{
  vi.mocked(api.listD5Measures).mockResolvedValue({legacy_text:null,items:[],total:21,page:1,page_size:20});
  render(<D5ProposalPanel capaId="report"/>);
  fireEvent.click(await screen.findByRole('button',{name:'下一页正式措施'}));
  await waitFor(()=>expect(api.listD5Measures).toHaveBeenLastCalledWith('report',2,expect.any(AbortSignal)));
  expect(api.listD5Proposals).toHaveBeenLastCalledWith('report',1,expect.any(AbortSignal));
});
it('clears the retained final draft and retry when a still-visible target loses adoption qualification',async()=>{
  vi.mocked(api.adoptD5Proposal).mockRejectedValue(new Error('lost response'));
  render(<D5ProposalPanel capaId="report"/>);
  await screen.findByText('Agent 原文',{selector:'p'});
  fireEvent.change(screen.getByLabelText('最终措施 p1'),{target:{value:'失权保留草稿'}});
  fireEvent.click(screen.getByRole('button',{name:'采纳 p1'}));
  await screen.findByRole('button',{name:'重试原处理'});
  vi.mocked(api.listD5Proposals).mockResolvedValue({items:[{...proposal,can_adopt:false}],total:1,page:1,page_size:20});
  await waitFor(()=>expect(screen.queryByDisplayValue('失权保留草稿')).toBeNull(),{timeout:3000});
  expect(screen.queryByRole('button',{name:'重试原处理'})).toBeNull();
});
