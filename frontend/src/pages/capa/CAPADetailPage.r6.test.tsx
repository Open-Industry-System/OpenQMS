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
import CAPADetailPage from "./CAPADetailPage";

const route = vi.hoisted(() => ({ id: "test-report-id" }));
const prerequisiteProbe = vi.hoisted(() => ({ before: null as null | (() => Promise<void>) }));
vi.mock("../../components/capa/D4RecPanel", async () => {
  const actual = await vi.importActual<typeof import("../../components/capa/D4RecPanel")>("../../components/capa/D4RecPanel");
  return { default: (props: any) => { prerequisiteProbe.before = props.beforeAdopt; return <actual.default {...props} />; } };
});
const verificationCard = vi.hoisted(() => vi.fn());
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
    useAuthStore.setState({user:{user_id:"u1",username:"engineer",role_key:"quality_engineer",permissions:{capa:3}} as any,token:"test-token"});
    mockSupplierOptions();
    vi.mocked(draftApi.getAIDraftCapabilities).mockResolvedValue({ai_draft_enabled:true,llm_provider:"openai"});
    vi.mocked(capaApi.getD4Recommendations).mockResolvedValue({items:[],stages:[]});
    vi.mocked(capaApi.getCapaOutcomeReview).mockResolvedValue({} as any);
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
