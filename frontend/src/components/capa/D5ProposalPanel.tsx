import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Button, Card } from 'antd';
import { adoptD5Proposal, checkpointProposals, listD5Proposals, listD5Measures, withdrawCheckpointProposals, withdrawD5Proposal } from '../../api/d5Proposals';
import type { D5BatchResult, D5Proposal, D5Measure } from '../../api/d5Proposals';
import { useAuthStore } from '../../store/authStore';
import { readAgentIdentity, readAgentCredential } from '../agent/useAgentTaskActivity';
import { useCapaChildRequests } from './useCapaViewRequests';
import { tr, useTr } from "../../i18n/tr";
interface Props {capaId:string; checkpoint?:{taskId:string;checkpointId:string}; onChanged?:()=>void;}
type Operation = {kind:'adopt'|'withdraw';id:string;key:string;value:string} | {kind:'batch';key:string;value:string;ids:string[]};
const labels = () => ({pending:tr("Zu prüfen", "Pending review"),adopted:tr("Übernommen", "Adopted"),withdrawn:tr("Zurückgezogen", "Withdrawn"),superseded:tr("Ersetzt", "Superseded")});
const readSession=()=>JSON.stringify([readAgentIdentity(),readAgentCredential()]);
function subscribeSession(callback:()=>void){
  const unsubscribe=useAuthStore.subscribe(callback);
  window.addEventListener('storage',callback);
  const timer=setInterval(callback,250);
  return ()=>{unsubscribe();window.removeEventListener('storage',callback);clearInterval(timer);};
}
const bounded = (s:string) => !!s.trim() && new TextEncoder().encode(s).length<=16384;
export default function D5ProposalPanel({capaId,checkpoint,onChanged}:Props) {
  useTr();
  const session=useSyncExternalStore(subscribeSession,readSession,readSession);
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
    setSnapshot(null);setEdits({});setReasons({});setSelected([]);setReason('');setResults([]);setRetry(null);setNotice('');setBusy(false);busyRef.current=false;
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
          setNotice(tr("Vorschläge nicht verfügbar; alter Text wurde entfernt, bitte Berechtigungen prüfen.", "Proposals unavailable; old text cleared, please check your permissions."));
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
    busyRef.current=true;setBusy(true);setNotice(tr("Wird gesendet", "Submitting"));
    try {
      if(op.kind==='batch'){
        if(!checkpoint)return;
        const value=await withdrawCheckpointProposals(checkpoint.taskId,checkpoint.checkpointId,{operation_key:op.key,reason:op.value,proposal_ids:op.ids},request.signal);
        if(request.current())setResults(value);
      }else if(op.kind==='adopt') await adoptD5Proposal(capaId,op.id,{operation_key:op.key,final_text:op.value},request.signal);
      else await withdrawD5Proposal(capaId,op.id,{operation_key:op.key,reason:op.value},request.signal);
      if(request.current()){setRetry(null);setNotice(tr("Verarbeitung bestätigt", "Processing confirmed"));setSnapshot(null);setEdits({});setReasons({});setSelected([]);setVersion(n=>n+1);onChanged?.();}
    }catch(error){
      if(!request.current())return;
      const status=(error as {response?:{status?:number}})?.response?.status;
      if(status && [401,403,404,409,422].includes(status)){
        setRetry(null);setSnapshot(null);setEdits({});setReasons({});setSelected([]);setResults([]);setNotice(tr("Berechtigung oder Status hat sich geändert, Vorschläge werden neu geladen.", "Eligibility or state changed, refreshing proposals."));setVersion(n=>n+1);
      }else{setRetry(op);setNotice(tr("Vorgang noch nicht bestätigt; Wiederholen sendet die ursprüngliche Anfrage.", "Operation not confirmed yet; retry sends the original request."));}
    }finally{if(request.current()){busyRef.current=false;setBusy(false);}request.finish();}
  }
  return <Card size="small" title={tr("Agent-D5-Vorschläge", "Agent D5 proposals")} style={{marginBottom:16}}>
    <p>{tr("Vorschläge gehören zu diesem Bericht; nach Ende der Aufgabe werden sie weiterhin einzeln nach aktueller Berechtigung bearbeitet.", "Proposals belong to this report; after the task ends they are still handled one by one per current eligibility.")}</p>
    <Button disabled={busy || !!retry} onClick={()=>{requests.invalidate();setSnapshot(null);setEdits({});setReasons({});setSelected([]);setResults([]);setRetry(null);setVersion(v=>v+1);}}>{tr("Vorschläge aktualisieren", "Refresh proposals")}</Button>
    {items.map(item=><section key={item.proposal_id} aria-label={tr(`Vorschlag ${item.proposal_id}`, `Proposal ${item.proposal_id}`)}>
      <p>{labels()[item.state]}{!item.basis_current && <> · <span>{tr("Grundlage veraltet", "Basis outdated")}</span></>}</p>
      <p>{tr("Vorschlag", "Proposal")} {item.proposal_id} · {tr("Aufgabe", "Task")} {item.task_id}</p><p>{item.original_text}</p>
      {checkpoint && <label><input type="checkbox" aria-label={tr(`Vorschlag ${item.proposal_id} auswählen`, `Select proposal ${item.proposal_id}`)} disabled={busy || !!retry || !item.can_withdraw} checked={selected.includes(item.proposal_id)} onChange={e=>setSelected(old=>e.target.checked?[...old,item.proposal_id]:old.filter(id=>id!==item.proposal_id))}/>{tr("Vorschlag auswählen", "Select proposal")}</label>}
      {item.state==='pending' && <>
        <label>{tr("Endgültige Maßnahme", "Final measure")}<textarea aria-label={tr(`Endgültige Maßnahme ${item.proposal_id}`, `Final measure ${item.proposal_id}`)} value={edits[item.proposal_id]??item.original_text} disabled={busy || !!retry || !item.can_adopt} onChange={e=>setEdits({...edits,[item.proposal_id]:e.target.value})}/></label>
        <Button aria-label={tr(`Übernehmen ${item.proposal_id}`, `Adopt ${item.proposal_id}`)} disabled={busy || !!retry || !item.can_adopt || !bounded(edits[item.proposal_id]??item.original_text)} onClick={()=>void execute({kind:'adopt',id:item.proposal_id,key:crypto.randomUUID(),value:edits[item.proposal_id]??item.original_text})}>{tr("Übernehmen", "Adopt")}</Button>
        <label>{tr("Rückzugsgrund", "Withdrawal reason")}<textarea aria-label={tr(`Rückzugsgrund ${item.proposal_id}`, `Withdrawal reason ${item.proposal_id}`)} value={reasons[item.proposal_id]??''} disabled={busy || !!retry || !item.can_withdraw} onChange={e=>setReasons({...reasons,[item.proposal_id]:e.target.value})}/></label>
        <Button aria-label={tr(`Zurückziehen ${item.proposal_id}`, `Withdraw ${item.proposal_id}`)} disabled={busy || !!retry || !item.can_withdraw || !bounded(reasons[item.proposal_id]??'')} onClick={()=>void execute({kind:'withdraw',id:item.proposal_id,key:crypto.randomUUID(),value:reasons[item.proposal_id]})}>{tr("Zurückziehen", "Withdraw")}</Button>
      </>}
    </section>)}
    {checkpoint && <section aria-label={tr("Teilweiser Rückzug ab Checkpoint", "Partial withdrawal at checkpoint")}>
      <p>{tr("Zieht nur die ausgewählten Vorschläge nach dem aktuellen Checkpoint zurück und meldet das Ergebnis einzeln.", "Withdraws only the selected proposals after the current checkpoint and reports each result.")}</p>
      <label>{tr("Grund für Sammelrückzug", "Batch withdrawal reason")}<textarea aria-label={tr("Grund für Sammelrückzug", "Batch withdrawal reason")} value={snapshot?.owner===requests?reason:''} disabled={busy || !!retry} onChange={e=>setReason(e.target.value)}/></label>
      <Button disabled={snapshot?.owner!==requests || busy || !!retry || !selected.length || !bounded(reason)} onClick={()=>void execute({kind:'batch',ids:[...selected],key:crypto.randomUUID(),value:reason})}>{tr("Ausgewählte Vorschläge zurückziehen", "Withdraw selected proposals")}</Button>
      {(snapshot?.owner===requests?results:[]).map(result=><p key={result.proposal_id}>{result.proposal_id}：{result.outcome}</p>)}
    </section>}
    <p>{tr(`Vorschläge Seite ${page}`, `Proposals page ${page}`)}</p>
    <Button disabled={page<=1 || busy || !!retry} onClick={()=>setPage(p=>p-1)}>{tr("Vorherige Vorschlagsseite", "Previous proposal page")}</Button>
    <Button disabled={!snapshot || page*20>=snapshot.total || busy || !!retry} onClick={()=>setPage(p=>p+1)}>{tr("Nächste Vorschlagsseite", "Next proposal page")}</Button>
    <section aria-label={tr("Formale D5-Maßnahmen", "Formal D5 measures")}>
      <h4>{tr("Von Mitarbeitenden bestätigte formale Maßnahmen", "Formal measures confirmed by staff")}</h4>
      {(snapshot?.owner===requests?snapshot.measures:[]).map(measure=><section key={measure.measure_id} aria-label={tr(`Formale Maßnahme ${measure.measure_id}`, `Formal measure ${measure.measure_id}`)}>
        <p>{tr("Zugehöriger Vorschlag", "Corresponding proposal")} {measure.proposal_id}</p>
        <p>{measure.final_text}</p>
        <p>{tr("Übernommen von", "Adopted by")} {measure.adopted_by} · {measure.adopted_at}</p>
      </section>)}
      <p>{tr(`Formale Maßnahmen Seite ${measurePage}`, `Formal measures page ${measurePage}`)}</p>
      <Button disabled={measurePage<=1 || busy || !!retry} onClick={()=>setMeasurePage(p=>p-1)}>{tr("Vorherige Maßnahmenseite", "Previous measure page")}</Button>
      <Button disabled={!snapshot || measurePage*20>=snapshot.measureTotal || busy || !!retry} onClick={()=>setMeasurePage(p=>p+1)}>{tr("Nächste Maßnahmenseite", "Next measure page")}</Button>
    </section>
    {snapshot?.owner===requests && retry && <Button disabled={busy} onClick={()=>void execute(retry)}>{tr("Ursprünglichen Vorgang wiederholen", "Retry original operation")}</Button>}
    <p aria-live="polite">{notice}</p>
  </Card>;
}
