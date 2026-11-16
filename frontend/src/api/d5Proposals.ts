import client from './client';
export type D5ProposalState = 'pending' | 'adopted' | 'withdrawn' | 'superseded';
export interface D5Proposal {
  proposal_id:string; task_id:string; original_text:string; state:D5ProposalState;
  basis_current:boolean; can_adopt:boolean; can_withdraw:boolean; created_at:string;
}
export interface D5ProposalPage {items:D5Proposal[];total:number;page:number;page_size:number;}
export interface CheckpointProposal {proposal_id:string;state:D5ProposalState;sequence:number;}
export interface D5BatchResult {proposal_id:string;outcome:string;}
const states = ['pending','adopted','withdrawn','superseded'];
const record = (v:unknown):v is Record<string,unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
function proposal(v:unknown):v is D5Proposal {
  return record(v) && typeof v.proposal_id==='string' && typeof v.task_id==='string' && typeof v.original_text==='string'
    && new TextEncoder().encode(v.original_text).length<=16384 && states.includes(String(v.state))
    && typeof v.basis_current==='boolean' && typeof v.can_adopt==='boolean' && typeof v.can_withdraw==='boolean' && typeof v.created_at==='string';
}
export async function listD5Proposals(reportId:string, page=1, signal?:AbortSignal, filter?:{task_id:string;state:"pending"}):Promise<D5ProposalPage> {
  const v:unknown=(await client.get(`/capa/${reportId}/d5-proposals`,{params:{page,page_size:20,...filter},signal})).data;
  if (!record(v) || !Array.isArray(v.items) || !v.items.every(proposal) || v.items.length>20 || !Number.isSafeInteger(v.total) || v.page!==page || v.page_size!==20) throw new Error('Invalid D5 proposal page');
  return v as unknown as D5ProposalPage;
}
export async function adoptD5Proposal(reportId:string, id:string, body:{operation_key:string;final_text:string},signal?:AbortSignal):Promise<{proposal_id:string;state:string}> {
  const value:unknown = (await client.post(`/capa/${reportId}/d5-proposals/${id}/adopt`,body,{signal})).data;
  if (!record(value) || value.proposal_id!==id || value.state!=='adopted' || typeof value.measure_id!=='string') throw new Error('Invalid D5 adoption receipt');
  return value as unknown as {proposal_id:string;state:string};
}
export async function withdrawD5Proposal(reportId:string,id:string,body:{operation_key:string;reason:string},signal?:AbortSignal):Promise<{proposal_id:string;state:string}> {
  const value:unknown = (await client.post(`/capa/${reportId}/d5-proposals/${id}/withdraw`,body,{signal})).data;
  if (!record(value) || value.proposal_id!==id || value.state!=='withdrawn') throw new Error('Invalid D5 withdrawal receipt');
  return value as unknown as {proposal_id:string;state:string};
}
export async function checkpointProposals(taskId:string,checkpointId:string,signal?:AbortSignal):Promise<CheckpointProposal[]> {
  const v:unknown=(await client.get(`/agent/tasks/${taskId}/d5-checkpoints/${checkpointId}/proposals`,{signal})).data;
  if (!Array.isArray(v) || !v.every(i=>record(i) && typeof i.proposal_id==='string' && states.includes(String(i.state)) && Number.isSafeInteger(i.sequence))) throw new Error('Invalid checkpoint list');
  return v as CheckpointProposal[];
}
export async function withdrawCheckpointProposals(taskId:string,checkpointId:string,body:{operation_key:string;reason:string;proposal_ids:string[]},signal?:AbortSignal):Promise<D5BatchResult[]> {
  const v:unknown=(await client.post(`/agent/tasks/${taskId}/d5-checkpoints/${checkpointId}/proposals/withdraw`,body,{signal})).data;
  if (!Array.isArray(v) || !v.every(i=>record(i) && typeof i.proposal_id==='string' && ['withdrawn','adopted','superseded','unavailable','conflict'].includes(String(i.outcome)))) throw new Error('Invalid batch result');
  if(v.length!==body.proposal_ids.length || new Set(v.map(i=>i.proposal_id)).size!==v.length || v.some(i=>!body.proposal_ids.includes(i.proposal_id))) throw new Error('Invalid batch membership');
  return v as D5BatchResult[];
}

export interface D5Measure {measure_id:string;proposal_id:string;final_text:string;adopted_by:string;adopted_at:string;}
export interface D5MeasurePage {legacy_text:string|null;items:D5Measure[];total:number;page:number;page_size:number;}
export async function listD5Measures(reportId:string,page=1,signal?:AbortSignal):Promise<D5MeasurePage>{
  const value:unknown=(await client.get(`/capa/${reportId}/d5-measures`,{params:{page,page_size:20},signal})).data;
  if(!record(value) || !(value.legacy_text===null || typeof value.legacy_text==='string') || !Array.isArray(value.items) || value.items.length>20
    || !value.items.every(item=>record(item) && typeof item.measure_id==='string' && typeof item.proposal_id==='string' && typeof item.final_text==='string' && new TextEncoder().encode(item.final_text).length<=16384 && typeof item.adopted_by==='string' && typeof item.adopted_at==='string' && Number.isFinite(Date.parse(item.adopted_at)))
    || !Number.isSafeInteger(value.total) || Number(value.total)<0 || value.page!==page || value.page_size!==20)throw new Error('Invalid D5 measure page');
  return value as unknown as D5MeasurePage;
}

export async function listTaskD5Proposals(reportId:string,taskId:string,page=1,signal?:AbortSignal):Promise<D5ProposalPage>{
  const result=await listD5Proposals(reportId,page,signal,{task_id:taskId,state:'pending'});
  if(result.items.some(item=>item.task_id!==taskId || item.state!=='pending'))throw new Error('Invalid correction task page');
  return result;
}
