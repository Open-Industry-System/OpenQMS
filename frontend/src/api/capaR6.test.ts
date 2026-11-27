import { beforeEach, expect, it, vi } from 'vitest';
import client from './client';
import * as api from './capaR6';
vi.mock('./client',()=>({default:{get:vi.fn(),post:vi.fn()}}));
beforeEach(()=>vi.clearAllMocks());
it('sends only exact employee expectations and final wording',async()=>{
  const signal=new AbortController().signal;
  const body={operation_key:'same-key',expected_material_version:'material',expected_candidate_version:'candidate',mode:'append' as const,final_text:'员工根因'};
  vi.mocked(client.post).mockResolvedValue({data:{candidate_id:'candidate-id',root_revision_id:'revision',state:'adopted'}});
  await api.confirmD4('report','candidate-id',body,signal);
  expect(client.post).toHaveBeenCalledWith('/capa/report/d4-candidates/candidate-id/confirm',body,{signal});
});
it('binds every manual decision to local form and actual analysis identity',async()=>{
  const body={operation_key:'same-key',expected_material_version:'local-form',expected_analysis_id:'analysis'};
  vi.mocked(client.post).mockResolvedValue({data:{analysis_id:'analysis',decision_id:'decision',receipt_id:'receipt',decision:'passed',no_affected_confirmed:true,audit_run_id:null}});
  for(const action of ['audit','confirm-no-affected','defer','waiver'] as const){
    await api.manualDecision('report',action,body);
    expect(client.post).toHaveBeenLastCalledWith(`/capa/report/doc-gate/${action}`,body,{signal:undefined});
  }
});
it('rejects a source detail for another selected item before retaining its text',async()=>{
  vi.mocked(client.get).mockResolvedValue({data:{kind:'d4-candidate',item_id:'other',original_text:'hidden',sources:[],proof:{}}});
  await expect(api.getSourceDetails('report','d4-candidate','selected')).rejects.toThrow();
});
it('refuses incomplete or wrong-analysis manual receipts instead of claiming confirmation',async()=>{
 const body={operation_key:'key',expected_material_version:'local-form',expected_analysis_id:'analysis'};
 for(const receipt of [{},{analysis_id:'other',receipt_id:'r',decision_id:'d',decision:'passed',no_affected_confirmed:true,audit_run_id:null}]){
  vi.mocked(client.post).mockResolvedValue({data:receipt});
  await expect(api.manualDecision('report','confirm-no-affected',body)).rejects.toThrow();
 }
});
