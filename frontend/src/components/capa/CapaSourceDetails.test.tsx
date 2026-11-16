import {render,screen,fireEvent,waitFor,cleanup,act} from '@testing-library/react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import CapaSourceDetails from './CapaSourceDetails';
import * as api from '../../api/capaR6';
vi.mock('../../api/capaR6',()=>({getSourceDetails:vi.fn(),readEvidence:vi.fn()}));
const detail={kind:'d4-candidate' as const,item_id:'a',original_text:'来源原文',sources:[{source_id:'s',kind:'fmea_projection',projection_id:'fmea.failure_cause.reference.v1',version:'v',current_state:'stale',evidence:null,evidence_url:'/api/capa/report/sources/d4-candidate/a/evidence/s',fmea_id:'f',node_id:'n'}],proof:{state:'not_issued_by_confirmation',relation:'candidate_is_not_verification',bound_to_item:false}};
beforeEach(()=>{vi.clearAllMocks();vi.mocked(api.getSourceDetails).mockResolvedValue(detail);});afterEach(cleanup);
it('renders historical freshness and reauthorizes each source detail read',async()=>{
 vi.mocked(api.readEvidence).mockResolvedValue({...detail.sources[0],current_state:'current',evidence:{name:'受控证据'}});
 render(<CapaSourceDetails capaId="report" kind="d4-candidate" itemId="a"/>);
 expect(await screen.findByText(/stale/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'重新核对来源 s'}));
 await screen.findByText(/受控证据/);
 expect(api.readEvidence).toHaveBeenCalledWith('report','d4-candidate','a','s',expect.any(AbortSignal));
});
it('clears protected details on source revocation',async()=>{
 vi.mocked(api.readEvidence).mockRejectedValue({response:{status:403}});
 render(<CapaSourceDetails capaId="report" kind="d4-candidate" itemId="a"/>);await screen.findByText('来源原文');
 vi.mocked(api.getSourceDetails).mockRejectedValue({response:{status:403}});
 fireEvent.click(screen.getByRole('button',{name:'重新核对来源 s'}));
 await waitFor(()=>expect(screen.queryByText('来源原文')).toBeNull());
});
it('suppresses old selected source responses after item change',async()=>{
 let resolve!:(v:any)=>void;vi.mocked(api.getSourceDetails).mockReturnValueOnce(new Promise(r=>resolve=r)).mockRejectedValue({response:{status:403}});
 const view=render(<CapaSourceDetails capaId="report" kind="d4-candidate" itemId="a"/>);view.rerender(<CapaSourceDetails capaId="report" kind="d4-candidate" itemId="b"/>);
 await act(async()=>resolve(detail));expect(screen.queryByText('来源原文')).toBeNull();
});
