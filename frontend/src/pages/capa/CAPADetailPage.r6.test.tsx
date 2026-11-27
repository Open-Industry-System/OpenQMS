import { render, screen, fireEvent, waitFor, configure, act, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { App } from "antd";
import { useAuthStore } from "../../store/authStore";
import * as capaApi from "../../api/capa";
import * as draftApi from "../../api/capaDraft";
import * as knowledgeApi from "../../api/knowledge";
import { useProductLineStore } from "../../store/productLineStore";
import * as fmeaApi from "../../api/fmea";
import * as r6Api from "../../api/capaR6";
import CAPADetailPage from "./CAPADetailPage";

const route = vi.hoisted(() => ({ id: "test-report-id" }));
const prerequisiteProbe = vi.hoisted(() => ({ before: null as null | (() => Promise<void>) }));
vi.mock("../../components/capa/D4RecPanel", async () => {
  const actual = await vi.importActual<typeof import("../../components/capa/D4RecPanel")>("../../components/capa/D4RecPanel");
  return { default: (props: any) => { prerequisiteProbe.before = props.beforeAdopt; return <actual.default {...props} />; } };
});
const verificationCard = vi.hoisted(() => vi.fn());
const localClassification = vi.hoisted(() => ({publish:null as null|((value:boolean|null)=>void)}));
vi.mock('../../components/capa/CapaLocalClosure',async()=>{
  const actual=await vi.importActual<typeof import('../../components/capa/CapaLocalClosure')>('../../components/capa/CapaLocalClosure');
  return {default:(props:any)=>{localClassification.publish=props.onEligibility;return <actual.default {...props}/>;}};
});
const agentContext = vi.hoisted(() => ({ value: null as any }));
vi.mock("../../components/agent/AgentTaskContext", () => ({ useAgentTaskContext: () => agentContext.value }));
beforeEach(() => { agentContext.value = null; });

configure({ testIdAttribute: "data-e2e" });
afterAll(() => configure({ testIdAttribute: "data-testid" }));

// Mock react-router-dom params
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: route.id }),
    useNavigate: () => mockNavigate,
  };
});

// Mock APIs
vi.mock("../../api/capa", async () => {
  const actual = await vi.importActual<typeof import("../../api/capa")>("../../api/capa");
  return {
    ...actual,
    getCAPA: vi.fn(),
    getCapaOutcomeReview: vi.fn(),
    updateCAPA: vi.fn(),
    advanceCAPA: vi.fn(),
    confirmRepeat: vi.fn(),
    linkFMEA: vi.fn(),
    generatePpt: vi.fn(),
    getPptExportReviewReport: vi.fn(),
    triggerScar: vi.fn(),
    listCapaSupplierOptions: vi.fn(),
    sinkKnowledge: vi.fn(),
    getD3Runs: vi.fn(),
    getD3Adoptions: vi.fn(),
    getD3Executions: vi.fn(),
    getD3Snapshots: vi.fn(),
    getD3Report: vi.fn(),
    getD3Advice: vi.fn(),
    getD4Recommendations: vi.fn(),
    getD7Recommendations: vi.fn(),
    listD7Actions: vi.fn().mockResolvedValue([]),
    getDocGateImpact: vi.fn(),
    getDocGateAudit: vi.fn(),
    getDocGateDecision: vi.fn(),
    importD3Containment: vi.fn(),
  };
});
vi.mock("../../api/capaDraft");
vi.mock("../../api/capaR6", async () => ({
  ...await vi.importActual<typeof import("../../api/capaR6")>("../../api/capaR6"),
  getLocalClosure: vi.fn(),
}));
// This page suite owns its API fixtures. R5 panel behavior and real-client
// credential synchronization are covered by their dedicated composition suites.
vi.mock("../../api/d5Proposals", () => ({
  listD5Proposals: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  listD5Measures: vi.fn().mockResolvedValue({ legacy_text: null, items: [], total: 0, page: 1, page_size: 20 }),
  checkpointProposals: vi.fn().mockResolvedValue([]),
  adoptD5Proposal: vi.fn(),
  withdrawD5Proposal: vi.fn(),
  withdrawCheckpointProposals: vi.fn(),
}));
vi.mock("../../api/knowledge", () => ({
  findCapaKnowledgeEntry: vi.fn().mockResolvedValue(null),
  listKnowledgeEntries: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 }),
  getKnowledgeEntry: vi.fn(),
}));
vi.mock("../../api/fmea", () => ({
  listFMEAs: vi.fn().mockResolvedValue({ items: [] }),
}));

// Mock D4VerificationCard to avoid rendering issues
vi.mock("../../components/capa/D4VerificationCard", () => ({
  default: (props: unknown) => { verificationCard(props); return null; },
}));

const mockCapa = {
  report_id: "test-report-id",
  title: "Test CAPA Report",
  document_no: "8D-2026-001",
  status: "D2_DESCRIPTION",
  severity: "fatal",
  product_line_code: "DC-DC-100",
  fmea_ref_id: null,
  fmea_node_id: null,
  due_date: null,
  created_at: "2026-01-01T00:00:00Z",
  d1_team: [],
  d2_description: "",
  d3_interim: "",
  d4_root_cause: "",
  d5_correction: "",
  d6_verification: "",
  d7_prevention: "",
  d8_closure: "",
};

function renderPage() {
  return render(
    <App>
      <BrowserRouter>
        <CAPADetailPage />
      </BrowserRouter>
    </App>
  );
}

function mockSupplierOptions() {
  vi.mocked(capaApi.listCapaSupplierOptions).mockResolvedValue({
    items: [{ supplier_id: "sup-1", supplier_no: "S-001", name: "Acme", status: "approved" }],
    total: 1,
    page: 1,
    page_size: 50,
  } as any);
}

describe("R6 server entry phase", () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear();
    route.id='test-report-id';localClassification.publish=null;
    useAuthStore.setState({user:{user_id:"u1",username:"engineer",role_key:"quality_engineer",permissions:{capa:3}} as any,token:"test-token"});
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({ai_draft_enabled:true,llm_provider:"openai"});
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({items:[],stages:[]});
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({} as any);
    vi.mocked(r6Api.getLocalClosure).mockResolvedValue({eligible:false} as any);
  });
  function unfinishedD7(eligible:boolean){
    vi.mocked(capaApi.getCAPA).mockResolvedValue({...mockCapa,status:'D7_PREVENTION',entry_phase:'switched'} as any);
    vi.mocked(capaApi.getD7Recommendations).mockResolvedValue({recommendations:[{
      fmea_id:'fmea-a',failure_mode_node_id:'mode-a',failure_mode_name:'Unconfirmed legacy node',
      failure_cause_node_id:'cause-a',match_source:'linked',prevention_control_name:'existing control',
    }]} as any);
    vi.mocked(r6Api.getLocalClosure).mockResolvedValue({eligible,can_edit:true,material_version:'local-v1',
      can_save_prevention:true,can_save_manual_analysis:false,can_review_propagation:true,
      prevention:null,manual_analysis:null,propagation:null} as any);
  }
  it.each([true,false])('blocks fast D7 advance until classification resolves to %s',async eligible=>{
    unfinishedD7(false);let resolve!:(value:any)=>void;
    vi.mocked(r6Api.getLocalClosure).mockReturnValue(new Promise(value=>{resolve=value;}));
    vi.mocked(capaApi.advanceCAPA).mockResolvedValue({...mockCapa,status:'D7_COMPLETED'} as any);
    renderPage();await screen.findByText('Unconfirmed legacy node');
    expect(screen.getByTestId('capa-advance')).toBeDisabled();fireEvent.click(screen.getByTestId('capa-advance'));
    expect(capaApi.advanceCAPA).not.toHaveBeenCalled();expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await act(async()=>resolve({eligible,can_edit:true,material_version:'classified',can_save_prevention:true,
      can_save_manual_analysis:false,can_review_propagation:true,prevention:null,manual_analysis:null,propagation:null}));
    await waitFor(()=>expect(screen.getByTestId('capa-advance')).toBeEnabled());
    fireEvent.click(screen.getByTestId('capa-advance'));
    if(eligible)await waitFor(()=>expect(capaApi.advanceCAPA).toHaveBeenCalledWith(route.id,{target_state:'D7_COMPLETED'},expect.any(AbortSignal)));
    else{expect(await screen.findByRole('dialog')).toBeInTheDocument();expect(capaApi.advanceCAPA).not.toHaveBeenCalled();}
  });
  it('closes an ordinary skip modal and blocks old actions while classification is unavailable',async()=>{
    unfinishedD7(false);renderPage();await screen.findByText('Unconfirmed legacy node');
    fireEvent.click(screen.getByTestId('capa-advance'));await screen.findByRole('dialog');
    await act(async()=>localClassification.publish?.(null));
    expect(screen.getByTestId('capa-advance')).toBeDisabled();
    // Ant keeps the closing dialog mounted during its exit animation in jsdom.
    await waitFor(()=>expect(screen.getByRole('dialog').className).toContain('ant-zoom-leave'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Confirm Skip and Advance'}));
    expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
    expect(screen.getByTestId('d7-confirm')).toBeDisabled();expect(screen.getByTestId('d7-auto-fill')).toBeDisabled();
    fireEvent.click(screen.getByTestId('capa-advance'));expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
    await act(async()=>localClassification.publish?.(false));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Confirm Skip and Advance'}));
    expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
    await act(async()=>localClassification.publish?.(true));await waitFor(()=>expect(screen.getByTestId('capa-advance')).toBeEnabled());
    expect(screen.getByRole('dialog').className).toContain('ant-zoom-leave');
  });
  it('ignores a previous report classification callback and recovers only from the current owner',async()=>{
    unfinishedD7(false);const view=renderPage();await screen.findByText('Unconfirmed legacy node');
    const old=localClassification.publish;
    route.id='next-report-id';vi.mocked(capaApi.getCAPA).mockResolvedValue({...mockCapa,report_id:route.id,title:'Next report',status:'D7_PREVENTION'} as any);
    vi.mocked(r6Api.getLocalClosure).mockReturnValue(new Promise(()=>{}));
    view.rerender(<App><BrowserRouter><CAPADetailPage/></BrowserRouter></App>);
    await screen.findByText('Next report');await act(async()=>old?.(false));
    expect(screen.getByTestId('capa-advance')).toBeDisabled();expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await act(async()=>localClassification.publish?.(false));await waitFor(()=>expect(screen.getByTestId('capa-advance')).toBeEnabled());
  });
  it.each(['ordinary-recovery','confirm-before-commit'])('invalidates old skip intent during batched %s',async boundary=>{
    unfinishedD7(false);renderPage();await screen.findByText('Unconfirmed legacy node');
    fireEvent.click(screen.getByTestId('capa-advance'));const dialog=await screen.findByRole('dialog');
    const confirm=()=>fireEvent.click(within(dialog).getByRole('button',{name:'Confirm Skip and Advance'}));
    await act(async()=>{localClassification.publish?.(null);if(boundary==='ordinary-recovery')localClassification.publish?.(false);else confirm();});
    if(boundary==='ordinary-recovery')confirm();
    expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
  });
  it('clears classification when credentials change and ignores the old actor callback',async()=>{
    unfinishedD7(false);renderPage();await screen.findByText('Unconfirmed legacy node');
    await waitFor(()=>expect(screen.getByTestId('capa-advance')).toBeEnabled());
    const old=localClassification.publish;
    vi.mocked(r6Api.getLocalClosure).mockReturnValue(new Promise(()=>{}));
    await act(async()=>useAuthStore.setState({token:'next-actor-token'}));
    await act(async()=>old?.(false));
    expect(screen.getByTestId('capa-advance')).toBeDisabled();
    await act(async()=>localClassification.publish?.(false));
    await waitFor(()=>expect(screen.getByTestId('capa-advance')).toBeEnabled());
  });
  it('advances an eligible local D7 through the backend without legacy node skip payload',async()=>{
    unfinishedD7(true);
    vi.mocked(capaApi.advanceCAPA).mockResolvedValue({...mockCapa,status:'D7_COMPLETED'} as any);
    renderPage();await screen.findByLabelText('本地预防措施');await screen.findByText('Unconfirmed legacy node');
    fireEvent.click(screen.getByTestId('capa-advance'));
    await waitFor(()=>expect(capaApi.advanceCAPA).toHaveBeenCalledWith(route.id,{target_state:'D7_COMPLETED'},expect.any(AbortSignal)));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('retains the unconfirmed legacy node modal for an ordinary D7 report',async()=>{
    unfinishedD7(false);
    renderPage();await screen.findByText('Unconfirmed legacy node');
    fireEvent.click(screen.getByTestId('capa-advance'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();expect(capaApi.advanceCAPA).not.toHaveBeenCalled();
  });
  it('keeps an eligible local D7 pending when the authoritative backend rejects its local gate',async()=>{
    unfinishedD7(true);
    vi.mocked(capaApi.advanceCAPA).mockRejectedValue({response:{status:400,data:{detail:'LOCAL_PREVENTION_REQUIRED'}}});
    renderPage();await screen.findByLabelText('本地预防措施');await screen.findByText('Unconfirmed legacy node');
    fireEvent.click(screen.getByTestId('capa-advance'));
    await waitFor(()=>expect(capaApi.advanceCAPA).toHaveBeenCalledWith(route.id,{target_state:'D7_COMPLETED'},expect.any(AbortSignal)));
    await screen.findByText('LOCAL_PREVENTION_REQUIRED');expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it("uses switched server phase to hide D4 old recommendation and draft actions", async () => {
    vi.mocked(capaApi.getCAPA).mockResolvedValue({...mockCapa,status:"D4_ROOT_CAUSE",d4_root_cause:"original",entry_phase:"switched",entry_epoch:2,material_version:"v2"} as any);
    renderPage();
    await screen.findByText("Test CAPA Report");
    await waitFor(() => expect(capaApi.getCAPA).toHaveBeenCalled());
    expect(capaApi.getD4Recommendations).not.toHaveBeenCalled();
    expect(screen.queryByTestId("capa-ai-draft")).not.toBeInTheDocument();
  });
  it("sends current material and switch epoch on ordinary manual D4 edit", async () => {
    vi.mocked(capaApi.getCAPA).mockResolvedValue({...mockCapa,status:"D4_ROOT_CAUSE",d4_root_cause:"original",entry_phase:"switched",entry_epoch:2,material_version:"v2"} as any);
    vi.mocked(capaApi.updateCAPA).mockResolvedValue({...mockCapa,status:"D4_ROOT_CAUSE",d4_root_cause:"manual",entry_phase:"switched",entry_epoch:2,material_version:"v3"} as any);
    renderPage();
    const field=await screen.findByDisplayValue("original");
    fireEvent.change(field,{target:{value:"manual"}}); fireEvent.blur(field);
    await waitFor(() => expect(capaApi.updateCAPA).toHaveBeenCalledWith("test-report-id",{d4_root_cause:"manual",expected_material_version:"v2",expected_entry_epoch:2},expect.any(AbortSignal)));
  });
});
vi.mock('../../api/capaR6',()=>({listD4Candidates:vi.fn().mockResolvedValue({items:[],page:1,page_size:20}),getLocalClosure:vi.fn().mockResolvedValue({eligible:false,can_edit:false,material_version:'m',prevention:null,manual_analysis:null,propagation:null}),getMeasure:vi.fn(),getMeasureHistory:vi.fn(),correctD5:vi.fn()}));

describe('R6 manual conflict review',()=>{
  it('keeps typed text and requires explicit comparison before retry',async()=>{
    vi.clearAllMocks();localStorage.clear();
    useAuthStore.setState({user:{user_id:'u1',role_key:'admin',permissions:{capa:5}} as any,token:'credential-A'});
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({ai_draft_enabled:false,llm_provider:null});
    const original={...mockCapa,status:'D4_ROOT_CAUSE',d4_root_cause:'original',entry_phase:'switched',entry_epoch:2,material_version:'v2'};
    const current={...original,d4_root_cause:'other employee text',material_version:'v3'};
    vi.mocked(capaApi.getCAPA).mockResolvedValueOnce(original as any).mockResolvedValue(current as any);
    vi.mocked(capaApi.updateCAPA).mockRejectedValueOnce({response:{status:409}}).mockResolvedValue({...current,d4_root_cause:'my typed text',material_version:'v4'} as any);
    renderPage();const field=await screen.findByDisplayValue('original');
    fireEvent.change(field,{target:{value:'my typed text'}});fireEvent.blur(field);
    await screen.findByText('other employee text');
    expect(field).toHaveValue('my typed text');
    expect(capaApi.updateCAPA).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'核对后保存我的输入'}));
    await waitFor(()=>expect(capaApi.updateCAPA).toHaveBeenLastCalledWith('test-report-id',{
      d4_root_cause:'my typed text',expected_material_version:'v3',expected_entry_epoch:2},expect.any(AbortSignal)));
  });
});

const refreshProbe=vi.hoisted(()=>({refresh:null as null|(()=>Promise<void>)}));
vi.mock('../../components/capa/D4CandidatePanel',()=>({default:(props:any)=>{refreshProbe.refresh=props.onChanged;return <div/>;}}));

describe('R6 learned retirement is monotonic',()=>{
  it('legacy409 then switched refresh cannot reuse an old AI preview with new manual tokens',async()=>{
    vi.clearAllMocks();localStorage.clear();
    useAuthStore.setState({user:{user_id:'u1',role_key:'admin',permissions:{capa:5}} as any,token:'credential-A'});
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({ai_draft_enabled:true,llm_provider:'synthetic'});
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({items:[],stages:[]});
    const legacy={...mockCapa,status:'D4_ROOT_CAUSE',d4_root_cause:'original',entry_phase:'legacy',entry_epoch:0,material_version:'v0'};
    const changed={...legacy,d4_root_cause:'other employee text',material_version:'v1'};
    const switched={...changed,entry_phase:'switched',entry_epoch:2,material_version:'v2'};
    vi.mocked(capaApi.getCAPA).mockResolvedValueOnce(legacy as any).mockResolvedValueOnce(changed as any).mockResolvedValue(switched as any);
    vi.mocked(capaApi.updateCAPA).mockRejectedValueOnce({response:{status:409}}).mockResolvedValue(switched as any);
    vi.mocked(draftApi.generateDraft).mockResolvedValue({content:'OLD_PRE_SWITCH_DRAFT',structured_data:null,request_id:'old',step:'d4'});
    renderPage();const field=await screen.findByDisplayValue('original');
    fireEvent.change(field,{target:{value:'manual input'}});fireEvent.blur(field);
    await screen.findByText('other employee text');
    fireEvent.click(screen.getByRole('button',{name:'保留输入，稍后处理'}));
    fireEvent.click(await screen.findByText('AI Draft'));
    await screen.findByText('OLD_PRE_SWITCH_DRAFT');
    const replace=screen.getByRole('button',{name:/Replace/i});
    await act(async()=>{await refreshProbe.refresh?.();});
    if(replace.isConnected)fireEvent.click(replace);
    await act(async()=>{});
    expect(capaApi.updateCAPA).toHaveBeenCalledTimes(1);
    await waitFor(()=>expect(screen.queryByText('OLD_PRE_SWITCH_DRAFT')).not.toBeInTheDocument());
    expect(screen.queryByTestId('capa-ai-draft')).not.toBeInTheDocument();
  });
});
