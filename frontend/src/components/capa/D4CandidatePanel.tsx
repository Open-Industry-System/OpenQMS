import {useTranslation} from 'react-i18next';
import {useEffect,useRef,useState} from 'react';
import {Button,Card} from 'antd';
import * as api from '../../api/capaR6';
import {useCapaCredentialIdentity} from './useCapaViewRequests';
import {boundedR6,useR6Resource} from './useR6Resource';
import CapaSourceDetails from './CapaSourceDetails';
export default function D4CandidatePanel({capaId,onChanged}:{capaId:string;onChanged?:()=>void}){
 const {identity}=useCapaCredentialIdentity();return <Panel key={identity+capaId} capaId={capaId} onChanged={onChanged}/>;
}
function Panel({capaId,onChanged}:{capaId:string;onChanged?:()=>void}){
 const {t}=useTranslation('capa');
 const [page,setPage]=useState(1);
 const resource=useR6Resource(capaId,String(page),signal=>api.listD4Candidates(capaId,page,signal));
 const selectedCandidate=useRef<string|null>(null);
 const contextRequest=useRef<{cancel:()=>void}|null>(null);
 const [context,setContext]=useState<{value:api.D4Confirmation;epoch:number}|null>(null);
 const [final,setFinal]=useState('');const [mode,setMode]=useState<'append'|'replace'>('append');const [replace,setReplace]=useState(false);
 const [reasons,setReasons]=useState<Record<string,string>>({});const [source,setSource]=useState<string|null>(null);
 useEffect(()=>{contextRequest.current?.cancel();selectedCandidate.current=null;setContext(null);setFinal('');setReasons({});setSource(null);},[resource.cleared]);
 useEffect(()=>()=>contextRequest.current?.cancel(),[]);
 const current=context?.epoch===resource.cleared&&context.value.candidate_id===selectedCandidate.current?context.value:null;
 async function open(item:api.D4Candidate){
  contextRequest.current?.cancel();
  selectedCandidate.current=item.candidate_id;
  setContext(null);setFinal('');setMode('append');setReplace(false);
  const req=resource.requests.begin();contextRequest.current=req;
  const currentSelection=()=>req.current()&&selectedCandidate.current===item.candidate_id&&contextRequest.current===req;
  try{
   const value=await api.getD4Confirmation(capaId,item.candidate_id,req.signal);
   if(currentSelection()){setContext({value,epoch:resource.cleared});setFinal(item.original_text);}
  }catch{if(currentSelection()){setContext(null);setFinal('');resource.refresh();}}
  finally{req.finish();}
 }

 return <Card title={t("r6.candidateTitle")}>
 <p>候选确认与验证、来源证明分别处理。新增事实请先维护 D2/D3/FMEA，再重新捕获；证明不足时请手工维护 D5。</p>
 <Button disabled={resource.busy||!!resource.retry} onClick={resource.refresh}>刷新候选</Button>
 {(resource.data?.items??[]).map(item=><section key={item.candidate_id}>
 <p>{item.original_text}</p><p>状态 {item.state} · 版本 {item.version}</p>
 <p>支持：{item.supporting.join('；')}</p><p>反对：{item.opposing.join('；')}</p><p>缺失信息：{item.missing_information.join('；')}</p>
 <Button onClick={()=>setSource(item.candidate_id)}>依据详情 {item.candidate_id}</Button>
 {item.can_confirm&&<Button aria-label={`核对并确认 ${item.candidate_id}`} disabled={resource.busy||!!resource.retry} onClick={()=>void open(item)}>核对并确认</Button>}
 {item.can_withdraw&&<><textarea aria-label={`撤回原因 ${item.candidate_id}`} disabled={resource.busy||!!resource.retry} value={reasons[item.candidate_id]??''} onChange={e=>setReasons({...reasons,[item.candidate_id]:e.target.value})}/><Button aria-label={`撤回 ${item.candidate_id}`} disabled={resource.busy||!!resource.retry||!boundedR6(reasons[item.candidate_id]??'')} onClick={()=>{const body={operation_key:crypto.randomUUID(),reason:reasons[item.candidate_id]};void resource.execute(signal=>api.withdrawD4(capaId,item.candidate_id,body,signal));}}>撤回</Button></>}
 </section>)}
 {resource.data&&current&&<section aria-label="根因确认表单">
 <label>最终根因<textarea aria-label="最终根因" value={final} disabled={resource.busy||!!resource.retry||!current.can_confirm} onChange={e=>setFinal(e.target.value)}/></label>
 <label>写入方式<select aria-label="写入方式" value={mode} disabled={resource.busy||!!resource.retry} onChange={e=>{setMode(e.target.value as typeof mode);setReplace(false);}}><option value="append">追加</option><option value="replace">替换全文</option></select></label>
 {mode==='replace'&&<><h4>当前全文 → 替换后全文</h4><pre>{current.current_root_text}</pre><pre>{final}</pre><label><input type="checkbox" aria-label="已核对全文替换差异" checked={replace} onChange={e=>setReplace(e.target.checked)}/>已核对全文替换差异</label></>}
 {current.can_confirm&&<Button disabled={resource.busy||!!resource.retry||!boundedR6(final)||(mode==='replace'&&!replace)} onClick={()=>{const body={operation_key:crypto.randomUUID(),expected_material_version:current.material_version,expected_candidate_version:current.candidate_version,mode,final_text:final};void resource.execute(async signal=>{await api.confirmD4(capaId,current.candidate_id,body,signal);onChanged?.();});}}>确认正式根因</Button>}
 </section>}
 {resource.data&&source&&<CapaSourceDetails capaId={capaId} kind="d4-candidate" itemId={source}/>}
 <p>候选第 {page} 页</p><Button disabled={page===1||resource.busy||!!resource.retry} onClick={()=>setPage(p=>p-1)}>上一页候选</Button><Button disabled={(resource.data?.items.length??0)<20||resource.busy||!!resource.retry} onClick={()=>setPage(p=>p+1)}>下一页候选</Button>
 {resource.data&&resource.retry&&<Button disabled={resource.busy} onClick={()=>void resource.execute(resource.retry!.run)}>重试原请求</Button>}<p role="status">{resource.notice}</p>
 </Card>;
}
