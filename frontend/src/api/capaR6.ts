import client from './client';
export type SourceKind='d4-candidate'|'d5-proposal'|'d5-measure';
export interface Expectation {operation_key:string;expected_material_version:string;}
export interface D4Candidate {candidate_id:string;state:'pending'|'adopted'|'withdrawn'|'superseded';version:string;material_version:string;original_text:string;supporting:string[];opposing:string[];missing_information:string[];can_confirm:boolean;can_withdraw:boolean;}
export interface SourceDetail {kind:SourceKind;item_id:string;original_text:string;sources:{source_id:string;kind:string;projection_id:string;version:string;current_state:string;evidence:unknown;evidence_url:string;fmea_id?:string;node_id?:string;snapshot_id?:string;}[];proof:Record<string,unknown>;}
export interface Measure {measure_id:string;proposal_id:string;final_text:string;adopted_text:string;adopted_by:string;adopted_at:string;current_version:string;material_version:string;can_correct:boolean;correction_revision_id:string|null;correction_revision_no:number;}
export interface MeasureHistory {measure_id:string;final_text:string;adopted_text:string;adopted_by:string;adopted_at:string;current_version:string;corrections:{revision_id:string;revision_no:number;final_text:string;reason:string;actor_id:string;created_at:string;}[];}
export interface LocalRecord {revision_id:string;revision_no:number;reason:string;text:string|null;basis:string|null;analysis_id:string|null;analysis_method:string|null;channels:Record<string,unknown>|null;input_bindings:Record<string,unknown>;candidates:Record<string,unknown>[];sources:Record<string,unknown>[];report_snapshot_sources?:Record<string,unknown>[];}
export interface LocalClosure {eligible:boolean;material_version:string;can_edit:boolean;can_waive?:boolean;can_save_prevention:boolean;can_save_manual_analysis:boolean;can_review_propagation:boolean;prevention:LocalRecord|null;manual_analysis:LocalRecord|null;propagation:LocalRecord|null;current_candidates?:Record<string,unknown>[];}
const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const str=(v:unknown):v is string=>typeof v==='string'&&new TextEncoder().encode(v).length<=65536;
const texts=(v:unknown)=>Array.isArray(v)&&v.length<=20&&v.every(str);
function requireValue<T>(v:unknown,valid:boolean):T{if(!valid)throw new Error('R6 response invalid');return v as T;}
export async function listD4Candidates(report:string,page=1,signal?:AbortSignal){
 const v=(await client.get(`/capa/${report}/d4-candidates`,{params:{page,page_size:20},signal})).data;
 return requireValue<{items:D4Candidate[];page:number;page_size:number}>(v,obj(v)&&v.page===page&&v.page_size===20&&Array.isArray(v.items)&&v.items.length<=20&&v.items.every((r:unknown)=>obj(r)&&str(r.candidate_id)&&str(r.original_text)&&str(r.version)&&str(r.material_version)&&['pending','adopted','withdrawn','superseded'].includes(r.state)&&texts(r.supporting)&&texts(r.opposing)&&texts(r.missing_information)&&typeof r.can_confirm==='boolean'&&typeof r.can_withdraw==='boolean'));
}
export async function confirmD4(report:string,id:string,body:Expectation&{expected_candidate_version:string;mode:'append'|'replace';final_text:string},signal?:AbortSignal){
 const v=(await client.post(`/capa/${report}/d4-candidates/${id}/confirm`,body,{signal})).data;
 return requireValue(v,obj(v)&&v.candidate_id===id&&str(v.root_revision_id));
}
export async function withdrawD4(report:string,id:string,body:{operation_key:string;reason:string},signal?:AbortSignal){return (await client.post(`/capa/${report}/d4-candidates/${id}/withdraw`,body,{signal})).data;}
export async function getSourceDetails(report:string,kind:SourceKind,id:string,signal?:AbortSignal){
 const v=(await client.get(`/capa/${report}/sources/${kind}/${id}`,{signal})).data;
 return requireValue<SourceDetail>(v,obj(v)&&v.kind===kind&&v.item_id===id&&str(v.original_text)&&obj(v.proof)&&Array.isArray(v.sources)&&v.sources.length<=1000&&v.sources.every((r:unknown)=>obj(r)&&str(r.source_id)&&['fmea_projection','report_snapshot'].includes(r.kind)&&str(r.projection_id)&&str(r.version)&&['current','stale','unavailable'].includes(r.current_state)&&r.evidence_url===`/api/capa/${report}/sources/${kind}/${id}/evidence/${r.source_id}`));
}
export async function readEvidence(report:string,kind:SourceKind,id:string,sourceId:string,signal?:AbortSignal){
 const v=(await client.get(`/capa/${report}/sources/${kind}/${id}/evidence/${sourceId}`,{signal})).data;
 return requireValue<SourceDetail['sources'][number]>(v,obj(v)&&v.source_id===sourceId&&['current','stale','unavailable'].includes(v.current_state));
}
export async function getMeasure(report:string,id:string,signal?:AbortSignal){
 const v=(await client.get(`/capa/${report}/d5-measures/${id}`,{signal})).data;
 return requireValue<Measure>(v,obj(v)&&v.measure_id===id&&str(v.final_text)&&str(v.adopted_text)&&str(v.current_version)&&str(v.material_version)&&typeof v.can_correct==='boolean'&&Number.isSafeInteger(v.correction_revision_no));
}
export async function getMeasureHistory(report:string,id:string,signal?:AbortSignal){
 const v=(await client.get(`/capa/${report}/d5-measures/${id}/corrections`,{signal})).data;
 return requireValue<MeasureHistory>(v,obj(v)&&v.measure_id===id&&str(v.final_text)&&str(v.adopted_text)&&str(v.current_version)&&Array.isArray(v.corrections)&&v.corrections.every((r:unknown)=>obj(r)&&str(r.revision_id)&&Number.isSafeInteger(r.revision_no)&&r.revision_no>0&&str(r.final_text)&&str(r.reason)&&str(r.actor_id)&&str(r.created_at)));
}
export async function correctD5(report:string,id:string,body:Expectation&{expected_measure_version:string;final_text:string;reason:string},signal?:AbortSignal){return (await client.post(`/capa/${report}/d5-measures/${id}/corrections`,body,{signal})).data;}
export function validLocal(v:unknown):v is LocalClosure{
 return obj(v)&&typeof v.eligible==='boolean'&&str(v.material_version)&&typeof v.can_edit==='boolean'&&['can_save_prevention','can_save_manual_analysis','can_review_propagation','can_waive'].every(k=>typeof v[k]==='boolean')&&['prevention','manual_analysis','propagation'].every(k=>v[k]===null||(obj(v[k])&&str(v[k].revision_id)&&Number.isSafeInteger(v[k].revision_no)&&v[k].revision_no>0&&str(v[k].reason)&&obj(v[k].input_bindings)&&(v[k].channels===null||obj(v[k].channels))&&Array.isArray(v[k].sources)&&Array.isArray(v[k].candidates)&&(v[k].analysis_id===null||str(v[k].analysis_id))));
}
export async function getLocalClosure(report:string,signal?:AbortSignal){const v=(await client.get(`/capa/${report}/local-closure`,{signal})).data;return requireValue<LocalClosure>(v,validLocal(v));}
export async function saveLocal(report:string,kind:'local-prevention'|'manual-doc-analysis'|'propagation-review',body:Expectation&Record<string,unknown>,signal?:AbortSignal){return (await client.post(`/capa/${report}/${kind}`,body,{signal})).data;}
export async function manualDecision(report:string,action:'audit'|'confirm-no-affected'|'defer'|'waiver',body:Expectation&{expected_analysis_id:string}&Record<string,unknown>,signal?:AbortSignal){
 const v=(await client.post(`/capa/${report}/doc-gate/${action}`,body,{signal})).data;
 return requireValue<Record<string,unknown>>(v,obj(v)&&v.analysis_id===body.expected_analysis_id&&str(v.receipt_id)&&str(v.decision_id)&&['passed','blocked','deferred'].includes(v.decision)&&typeof v.no_affected_confirmed==='boolean'&&(v.audit_run_id===null||str(v.audit_run_id)));
}
export interface D4Confirmation {candidate_id:string;current_root_text:string|null;material_version:string;candidate_version:string;can_confirm:boolean;}
export async function getD4Confirmation(report:string,id:string,signal?:AbortSignal){const v=(await client.get(`/capa/${report}/d4-candidates/${id}/confirmation-context`,{signal})).data;return requireValue<D4Confirmation>(v,obj(v)&&v.candidate_id===id&&(v.current_root_text===null||str(v.current_root_text))&&str(v.material_version)&&str(v.candidate_version)&&typeof v.can_confirm==='boolean');}
export interface ManualCandidate {doc_id:string;doc_type:'fmea'|'control_plan';doc_name:string;baseline_version:unknown;existing_targets:{target_key:string;allowed_fields:string[]}[];add_anchors:{parent_node_id:string;node_type:string}[];}
export async function getManualCatalog(report:string,signal?:AbortSignal){const v=(await client.get(`/capa/${report}/manual-doc-catalog`,{signal})).data;return requireValue<{material_version:string;items:ManualCandidate[]}>(v,obj(v)&&str(v.material_version)&&Array.isArray(v.items)&&v.items.length<=1000&&v.items.every((c:unknown)=>obj(c)&&str(c.doc_id)&&['fmea','control_plan'].includes(c.doc_type)&&str(c.doc_name)&&Array.isArray(c.existing_targets)&&Array.isArray(c.add_anchors)));}
