import {render,screen,fireEvent,waitFor,cleanup,act} from '@testing-library/react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import CapaLocalClosure from './CapaLocalClosure';
import * as api from '../../api/capaR6';
vi.mock('../../api/capaR6',()=>({getLocalClosure:vi.fn(),getManualCatalog:vi.fn(),saveLocal:vi.fn(),manualDecision:vi.fn()}));
vi.mock('../../api/capa',()=>({getDocGateDecision:vi.fn().mockResolvedValue({decision:null}),getDocGateAudit:vi.fn().mockResolvedValue({audit_run_id:null,audits:[]})}));
const record={revision_id:'revision',revision_no:1,reason:'独立现场核对',text:'本地预防',basis:'实物试验',analysis_id:null,analysis_method:null,channels:null,input_bindings:{},candidates:[],sources:[]};
const form={eligible:true,can_edit:true,can_save_prevention:true,can_save_manual_analysis:true,can_review_propagation:true,can_waive:false,material_version:'local-form',prevention:record,manual_analysis:null,propagation:null};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(api.getLocalClosure).mockResolvedValue(form);vi.mocked(api.getManualCatalog).mockResolvedValue({material_version:'local-form',items:[]});});afterEach(cleanup);
it('publishes unknown on load, refresh failure and credential-owned clearing, then recovers ordinary false',async()=>{
 const classify=vi.fn();let resolve!:(value:any)=>void;
 vi.mocked(api.getLocalClosure).mockReturnValue(new Promise(value=>{resolve=value;}));
 render(<CapaLocalClosure capaId="report" status="D7_PREVENTION" onEligibility={classify}/>);
 await waitFor(()=>expect(classify).toHaveBeenLastCalledWith(null));
 await act(async()=>resolve(form));
 await waitFor(()=>expect(classify).toHaveBeenLastCalledWith(true));
 vi.mocked(api.getLocalClosure).mockRejectedValue(new Error('source unavailable'));
 fireEvent.click(screen.getByRole('button',{name:'刷新本地材料'}));
 await waitFor(()=>expect(classify).toHaveBeenLastCalledWith(null));
 await screen.findByText('材料不可用，旧文本及版本已清除。');
 vi.mocked(api.getLocalClosure).mockResolvedValue({...form,eligible:false});
 fireEvent.click(screen.getByRole('button',{name:'刷新本地材料'}));
 await waitFor(()=>expect(classify).toHaveBeenLastCalledWith(false));
});
it('saves controlled prevention and never generic PUT copies',async()=>{
 render(<CapaLocalClosure capaId="report" status="D7_PREVENTION"/>);
 fireEvent.change(await screen.findByLabelText('本地预防措施'),{target:{value:'预防现场措施'}});
 fireEvent.change(screen.getByLabelText('本地预防依据'),{target:{value:'现场依据'}});
 fireEvent.change(screen.getByLabelText('本地预防理由'),{target:{value:'现场理由'}});
 fireEvent.click(screen.getByRole('button',{name:'保存本地预防'}));
 await waitFor(()=>expect(api.saveLocal).toHaveBeenCalledWith('report','local-prevention',{operation_key:expect.any(String),expected_material_version:'local-form',text:'预防现场措施',basis:'现场依据',reason:'现场理由'},expect.any(AbortSignal)));
});
it('manual empty capture never implicitly confirms empty; explicit confirm uses local form and analysis',async()=>{
 const manual={...record,analysis_id:'manual-id',analysis_method:'manual',input_bindings:{affected_docs:[]}};
 vi.mocked(api.getLocalClosure).mockResolvedValue({...form,manual_analysis:manual});
 render(<CapaLocalClosure capaId="report" status="D8_GATE_PENDING"/>);
 await screen.findByText('人工分析已记录；模型未运行，尚须独立门禁处置。');
 expect(api.manualDecision).not.toHaveBeenCalled();
 fireEvent.click(screen.getByLabelText('独立确认本轮无受影响文档'));
 fireEvent.click(screen.getByRole('button',{name:'确认空清单'}));
 await waitFor(()=>expect(api.manualDecision).toHaveBeenCalledWith('report','confirm-no-affected',{operation_key:expect.any(String),expected_material_version:'local-form',expected_analysis_id:'manual-id'},expect.any(AbortSignal)));
});
it('VIEW displays local source restrictions but no mutation actions',async()=>{
 vi.mocked(api.getLocalClosure).mockResolvedValue({...form,can_edit:false,can_save_prevention:false,can_save_manual_analysis:false,can_review_propagation:false,propagation:{...record,channels:{lessons:'NOT_EXECUTED',knowledge:'NOT_EXECUTED',lateral:'NOT_EXECUTED',supplier_risk:'NOT_EXECUTED'}}});
 render(<CapaLocalClosure capaId="report" status="D7_PREVENTION"/>);
 await screen.findByText(/NOT_EXECUTED/);expect(screen.queryByRole('button',{name:'保存本地预防'})).toBeNull();
});

it('captures a real selected document with typed target and field rather than raw JSON',async()=>{
 vi.mocked(api.getManualCatalog).mockResolvedValue({material_version:'local-form',items:[{doc_id:'doc',doc_type:'fmea',doc_name:'工艺FMEA',baseline_version:{major:1},existing_targets:[{target_key:'cause',allowed_fields:['name']}],add_anchors:[]}]});
 render(<CapaLocalClosure capaId="report" status="D8_GATE_PENDING"/>);
 fireEvent.click(await screen.findByLabelText('选择受影响文档 doc'));
 fireEvent.change(screen.getByLabelText('更新建议 doc'),{target:{value:'修改原因措辞'}});
 fireEvent.change(screen.getByLabelText('目标 doc'),{target:{value:'cause'}});
 fireEvent.change(screen.getByLabelText('字段 doc'),{target:{value:'name'}});
 fireEvent.click(screen.getByRole('button',{name:'添加核对点'}));
 fireEvent.change(screen.getByLabelText('人工分析理由'),{target:{value:'现场核对完整候选清单'}});
 fireEvent.click(screen.getByRole('button',{name:'保存人工分析'}));
 await waitFor(()=>expect(api.saveLocal).toHaveBeenCalledWith('report','manual-doc-analysis',expect.objectContaining({expected_material_version:'local-form',affected_docs:[{doc_id:'doc',doc_type:'fmea',update_suggestion:'修改原因措辞',key_points:[{expected_action:'modify',target_kind:'fmea_node',target_key:'cause',field:'name'}]}]}),expect.any(AbortSignal)));
});

it('selects exact uncovered CP modify audit points for APPROVE-only narrow waiver',async()=>{
 const base=await import('../../api/capa');
 vi.mocked(api.getLocalClosure).mockResolvedValue({...form,can_waive:true,manual_analysis:{...record,analysis_id:'analysis',analysis_method:'manual',input_bindings:{affected_docs:[{doc_id:'cp'}]}}});
 vi.mocked(base.getDocGateDecision).mockResolvedValue({decision:'blocked'});
 vi.mocked(base.getDocGateAudit).mockResolvedValue({audit_run_id:null,audits:[{doc_type:'control_plan',doc_id:'cp',doc_name:'控制计划',status:'incomplete',version_bump:true,covered_count:0,total_count:1,coverage:[{covered:false,key_point:{expected_action:'modify',target_kind:'cp_item',target_key:'missing-item',field:'control_method'},evidence:''}]}]});
 render(<CapaLocalClosure capaId="report" status="D8_GATE_PENDING"/>);
 fireEvent.click(await screen.findByLabelText('豁免 cp missing-item control_method'));
 fireEvent.change(screen.getByLabelText('豁免理由'),{target:{value:'核对断链及剩余完整性'}});
 fireEvent.click(screen.getByRole('button',{name:'提交受限豁免'}));
 await waitFor(()=>expect(api.manualDecision).toHaveBeenCalledWith('report','waiver',expect.objectContaining({expected_material_version:'local-form',expected_analysis_id:'analysis',items:[{doc_type:'control_plan',doc_id:'cp',target_key:'missing-item',field:'control_method'}]}),expect.any(AbortSignal)));
});

it.each([{doc_type:'fmea' as const,target_kind:'fmea_node',field:'name',node_type:'FailureCause'},{doc_type:'control_plan' as const,target_kind:'cp_item',field:'control_method',node_type:'FailureMode'}])('sends strict typed add field for $doc_type',async({doc_type,target_kind,field,node_type})=>{
 const anchor={parent_node_id:'parent',node_type};
 vi.mocked(api.getManualCatalog).mockResolvedValue({material_version:'local-form',items:[{doc_id:'add-doc',doc_type,doc_name:'需新增的文档',baseline_version:{major:1},existing_targets:[],add_anchors:[anchor]}]});
 render(<CapaLocalClosure capaId="report" status="D8_GATE_PENDING"/>);
 fireEvent.click(await screen.findByLabelText('选择受影响文档 add-doc'));
 fireEvent.change(screen.getByLabelText('文档变更 add-doc'),{target:{value:'add'}});
 fireEvent.change(screen.getByLabelText('新增位置 add-doc'),{target:{value:JSON.stringify(anchor)}});
 fireEvent.change(screen.getByLabelText('业务标识 add-doc'),{target:{value:'new-business'}});
 expect(screen.getByRole('button',{name:'添加核对点'})).toBeDisabled();
 fireEvent.change(screen.getByLabelText('新增字段 add-doc'),{target:{value:field}});
 fireEvent.change(screen.getByLabelText('更新建议 add-doc'),{target:{value:'现场核对后新增'}});
 fireEvent.click(screen.getByRole('button',{name:'添加核对点'}));
 fireEvent.change(screen.getByLabelText('人工分析理由'),{target:{value:'核对完整候选目录'}});
 fireEvent.click(screen.getByRole('button',{name:'保存人工分析'}));
 await waitFor(()=>expect(api.saveLocal).toHaveBeenCalledWith('report','manual-doc-analysis',expect.objectContaining({affected_docs:[{doc_id:'add-doc',doc_type,update_suggestion:'现场核对后新增',key_points:[{expected_action:'add',target_kind,field,add_anchor:{...anchor,business_key:'new-business'}}]}]}),expect.any(AbortSignal)));
});
