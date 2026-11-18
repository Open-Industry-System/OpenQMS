import D5MeasureCorrection from './D5MeasureCorrection';
import CapaSourceDetails from './CapaSourceDetails';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Button, Card } from 'antd';
import { adoptD5Proposal, checkpointProposals, listD5Proposals, listD5Measures, withdrawCheckpointProposals, withdrawD5Proposal } from '../../api/d5Proposals';
import type { D5BatchResult, D5Proposal, D5Measure } from '../../api/d5Proposals';
import { useAuthStore } from '../../store/authStore';
import { readAgentIdentity, readAgentCredential } from '../agent/useAgentTaskActivity';
import { useCapaChildRequests } from './useCapaViewRequests';
interface Props {capaId:string; checkpoint?:{taskId:string;checkpointId:string}; onChanged?:()=>void;}
type Operation = {kind:'adopt'|'withdraw';id:string;key:string;value:string} | {kind:'batch';key:string;value:string;ids:string[]};
const labels = {pending:'待审',adopted:'已采纳',withdrawn:'已撤回',superseded:'已替代'};
const readSession=()=>JSON.stringify([readAgentIdentity(),readAgentCredential()]);
function subscribeSession(callback:()=>void){
  const unsubscribe=useAuthStore.subscribe(callback);
  window.addEventListener('storage',callback);
  const timer=setInterval(callback,250);
  return ()=>{unsubscribe();window.removeEventListener('storage',callback);clearInterval(timer);};
}
const bounded = (s:string) => !!s.trim() && new TextEncoder().encode(s).length<=16384;
export default function D5ProposalPanel({capaId,checkpoint,onChanged}:Props) {
  const session=useSyncExternalStore(subscribeSession,readSession,readSession);
  const [measureSelection,setMeasureSelection]=useState<string|null>(null);
  const [sourceSelection,setSourceSelection]=useState<string|null>(null);
  const [page,setPage]=useState(1);
  const [measurePage,setMeasurePage]=useState(1);
  const requests=useCapaChildRequests(capaId,JSON.stringify([checkpoint,page,measurePage,session]));
  const [snapshot,setSnapshot]=useState<{owner:typeof requests;items:D5Proposal[];total:number;measures:D5Measure[];measureTotal:number}|null>(null);
  const [edits,setEdits]=useState<Record<string,string>>({});
  const [reasons,setReasons]=useState<Record<string,string>>({});
  const [selected,setSelected]=useState<string[]>([]);
  const [reason,setReason]=useState('');
  const [results,setResults]=useState<D5BatchResult[]>([]);
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [retry,setRetry]=useState<Operation|null>(null);
  const busyRef=useRef(false);
  const [version,setVersion]=useState(0);
  const items=snapshot?.owner===requests?snapshot.items:[];
  useEffect(()=>{
    setMeasureSelection(null);setSourceSelection(null);setSnapshot(null);setEdits({});setReasons({});setSelected([]);setReason('');setResults([]);setRetry(null);setNotice('');setBusy(false);busyRef.current=false;
  },[requests]);
  useEffect(()=>{
    let timer:ReturnType<typeof setTimeout>;
    const request=requests.begin();
    async function load(){
      try {
        const [data,formal]=await Promise.all([listD5Proposals(capaId,page,request.signal),listD5Measures(capaId,measurePage,request.signal)]);
        const range=checkpoint?await checkpointProposals(checkpoint.taskId,checkpoint.checkpointId,request.signal):null;
        if(!request.current()) return;
        const visible=range?data.items.filter(item=>range.some(ref=>ref.proposal_id===item.proposal_id)):data.items;
        setSnapshot({owner:requests,items:visible,total:data.total,measures:formal.items,measureTotal:formal.total});
        const editableIds=new Set(visible.filter(item=>item.state==='pending' && item.can_adopt).map(item=>item.proposal_id));
        const withdrawableIds=new Set(visible.filter(item=>item.state==='pending' && item.can_withdraw).map(item=>item.proposal_id));
        setRetry(old=>{
          if(!old)return null;
          const eligible=(id:string)=>visible.some(item=>item.proposal_id===id && item.state==='pending' && (old.kind==='adopt'?item.can_adopt:item.can_withdraw));
          return (old.kind==='batch'?old.ids.every(eligible):eligible(old.id))?old:null;
        });
        setEdits(old=>Object.fromEntries(Object.entries(old).filter(([id])=>editableIds.has(id))));
        setReasons(old=>Object.fromEntries(Object.entries(old).filter(([id])=>withdrawableIds.has(id))));
        setSelected(old=>old.filter(id=>visible.some(item=>item.proposal_id===id && item.can_withdraw)));
      } catch(error) {
        if(request.current()){
          setSnapshot(null);setEdits({});setReasons({});setSelected([]);
          setRetry(null);
          setNotice('建议不可用；已清除旧文本，请检查当前权限。');
        }
      } finally {if(request.current()) timer=setTimeout(load,2000);}
    }
    void load();
    return ()=>{clearTimeout(timer);request.cancel();};
  },[capaId,checkpoint?.taskId,checkpoint?.checkpointId,page,measurePage,requests,version]);
  async function execute(op:Operation){
    if(busyRef.current || snapshot?.owner!==requests) return;
    const request=requests.begin();
    if(!request.current()) return;
    busyRef.current=true;setBusy(true);setNotice('提交中');
    try {
      if(op.kind==='batch'){
        if(!checkpoint)return;
        const value=await withdrawCheckpointProposals(checkpoint.taskId,checkpoint.checkpointId,{operation_key:op.key,reason:op.value,proposal_ids:op.ids},request.signal);
        if(request.current())setResults(value);
      }else if(op.kind==='adopt') await adoptD5Proposal(capaId,op.id,{operation_key:op.key,final_text:op.value},request.signal);
      else await withdrawD5Proposal(capaId,op.id,{operation_key:op.key,reason:op.value},request.signal);
      if(request.current()){setRetry(null);setNotice('处理已确认');setSnapshot(null);setEdits({});setReasons({});setSelected([]);setVersion(n=>n+1);onChanged?.();}
    }catch(error){
      if(!request.current())return;
      const status=(error as {response?:{status?:number}})?.response?.status;
      if(status && [401,403,404,409,422].includes(status)){
        setRetry(null);setSnapshot(null);setEdits({});setReasons({});setSelected([]);setResults([]);setNotice('资格或状态已变化，正在刷新建议。');setVersion(n=>n+1);
      }else{setRetry(op);setNotice('操作尚未确认；重试会发送原请求。');}
    }finally{if(request.current()){busyRef.current=false;setBusy(false);}request.finish();}
  }
  return <Card size="small" title="Agent D5 建议" style={{marginBottom:16}}>
    <p>建议归属本报告；任务结束后仍按当前资格逐项处理。</p>
    <Button disabled={busy || !!retry} onClick={()=>{requests.invalidate();setSnapshot(null);setEdits({});setReasons({});setSelected([]);setResults([]);setRetry(null);setVersion(v=>v+1);}}>刷新建议</Button>
    {items.map(item=><section key={item.proposal_id} aria-label={`建议 ${item.proposal_id}`}>
      <p>{labels[item.state]}{!item.basis_current && <> · <span>依据过时</span></>}</p>
      <p>建议 {item.proposal_id} · 任务 {item.task_id}</p><p>{item.original_text}</p><Button onClick={()=>setSourceSelection(item.proposal_id)}>查看建议依据 {item.proposal_id}</Button>
      {checkpoint && <label><input type="checkbox" aria-label={`选择建议 ${item.proposal_id}`} disabled={busy || !!retry || !item.can_withdraw} checked={selected.includes(item.proposal_id)} onChange={e=>setSelected(old=>e.target.checked?[...old,item.proposal_id]:old.filter(id=>id!==item.proposal_id))}/>选择建议</label>}
      {item.state==='pending' && <>
        <label>最终措施<textarea aria-label={`最终措施 ${item.proposal_id}`} value={edits[item.proposal_id]??item.original_text} disabled={busy || !!retry || !item.can_adopt} onChange={e=>setEdits({...edits,[item.proposal_id]:e.target.value})}/></label>
        <Button aria-label={`采纳 ${item.proposal_id}`} disabled={busy || !!retry || !item.can_adopt || !bounded(edits[item.proposal_id]??item.original_text)} onClick={()=>void execute({kind:'adopt',id:item.proposal_id,key:crypto.randomUUID(),value:edits[item.proposal_id]??item.original_text})}>采纳</Button>
        <label>撤回原因<textarea aria-label={`撤回原因 ${item.proposal_id}`} value={reasons[item.proposal_id]??''} disabled={busy || !!retry || !item.can_withdraw} onChange={e=>setReasons({...reasons,[item.proposal_id]:e.target.value})}/></label>
        <Button aria-label={`撤回 ${item.proposal_id}`} disabled={busy || !!retry || !item.can_withdraw || !bounded(reasons[item.proposal_id]??'')} onClick={()=>void execute({kind:'withdraw',id:item.proposal_id,key:crypto.randomUUID(),value:reasons[item.proposal_id]})}>撤回</Button>
      </>}
    </section>)}
    {checkpoint && <section aria-label="检查点部分撤回">
      <p>仅撤回当前检查点之后选中的建议，逐项返回结果。</p>
      <label>批量撤回原因<textarea aria-label="批量撤回原因" value={snapshot?.owner===requests?reason:''} disabled={busy || !!retry} onChange={e=>setReason(e.target.value)}/></label>
      <Button disabled={snapshot?.owner!==requests || busy || !!retry || !selected.length || !bounded(reason)} onClick={()=>void execute({kind:'batch',ids:[...selected],key:crypto.randomUUID(),value:reason})}>撤回选中建议</Button>
      {(snapshot?.owner===requests?results:[]).map(result=><p key={result.proposal_id}>{result.proposal_id}：{result.outcome}</p>)}
    </section>}
    <p>建议第 {page} 页</p>
    <Button disabled={page<=1 || busy || !!retry} onClick={()=>setPage(p=>p-1)}>上一页建议</Button>
    <Button disabled={!snapshot || page*20>=snapshot.total || busy || !!retry} onClick={()=>setPage(p=>p+1)}>下一页建议</Button>
    <section aria-label="正式 D5 措施">
      <h4>员工确认的正式措施</h4>
      {(snapshot?.owner===requests?snapshot.measures:[]).map(measure=><section key={measure.measure_id} aria-label={`正式措施 ${measure.measure_id}`}>
        <p>对应建议 {measure.proposal_id}</p>
        <p>{measure.final_text}</p><Button aria-label={`更正与历史 ${measure.measure_id}`} onClick={()=>setMeasureSelection(measure.measure_id)}>更正与历史</Button>
        <p>采纳人 {measure.adopted_by} · {measure.adopted_at}</p>
      </section>)}
      <p>正式措施第 {measurePage} 页</p>
      <Button disabled={measurePage<=1 || busy || !!retry} onClick={()=>setMeasurePage(p=>p-1)}>上一页正式措施</Button>
      <Button disabled={!snapshot || measurePage*20>=snapshot.measureTotal || busy || !!retry} onClick={()=>setMeasurePage(p=>p+1)}>下一页正式措施</Button>
    </section>
    {snapshot?.owner===requests && measureSelection && snapshot.measures.some(item=>item.measure_id===measureSelection) && <D5MeasureCorrection capaId={capaId} measureId={measureSelection} onChanged={onChanged}/>}
    {snapshot?.owner===requests && sourceSelection && snapshot.items.some(item=>item.proposal_id===sourceSelection) && <CapaSourceDetails capaId={capaId} kind="d5-proposal" itemId={sourceSelection}/>}
    {snapshot?.owner===requests && retry && <Button disabled={busy} onClick={()=>void execute(retry)}>重试原处理</Button>}
    <p aria-live="polite">{notice}</p>
  </Card>;
}
