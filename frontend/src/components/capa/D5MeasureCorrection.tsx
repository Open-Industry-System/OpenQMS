import {useTranslation} from 'react-i18next';
import {useEffect,useState} from 'react';
import {Button,Card} from 'antd';
import * as api from '../../api/capaR6';
import {useCapaCredentialIdentity} from './useCapaViewRequests';
import {boundedR6,useR6Resource} from './useR6Resource';
import CapaSourceDetails from './CapaSourceDetails';
interface Props{capaId:string;measureId:string;onChanged?:()=>void;}
export default function D5MeasureCorrection(props:Props){const {identity}=useCapaCredentialIdentity();return <Correction key={identity+props.capaId+props.measureId} {...props}/>;}
function Correction({capaId,measureId,onChanged}:Props){
 const {t}=useTranslation('capa');
 const resource=useR6Resource(capaId,measureId,async signal=>{
 const [measure,history]=await Promise.all([api.getMeasure(capaId,measureId,signal),api.getMeasureHistory(capaId,measureId,signal)]);
 if(measure.current_version!==history.current_version)throw new Error('Measure changed');return {measure,history};});
 const [final,setFinal]=useState('');const [edited,setEdited]=useState(false);const [reason,setReason]=useState('');const [sources,setSources]=useState(false);
 useEffect(()=>{setFinal('');setEdited(false);setReason('');setSources(false);},[resource.cleared]);
 const measure=resource.data?.measure;const history=resource.data?.history;
 return <Card title={t("r6.measureTitle")} size="small">
 <Button disabled={resource.busy||!!resource.retry} onClick={resource.refresh}>刷新正式措施</Button>
 {measure&&history&&<><p>当前文本 · 版本 {measure.current_version}</p><p>{measure.final_text}</p>
 <h4>采纳及更正历史</h4><p>{history.adopted_text}</p><p>采纳人 {history.adopted_by} · {history.adopted_at}</p>
 {history.corrections.map(row=><section key={row.revision_id}><p>更正版本 {row.revision_no} · {row.actor_id} · {row.created_at}</p><p>{row.final_text}</p><p>{row.reason}</p></section>)}
 <Button onClick={()=>setSources(v=>!v)}>查看正式措施依据</Button>{sources&&<CapaSourceDetails capaId={capaId} kind="d5-measure" itemId={measureId}/>}
 {measure.can_correct&&<><label>更正后全文<textarea aria-label="更正后全文" disabled={resource.busy||!!resource.retry} value={edited?final:measure.final_text} onChange={e=>{setFinal(e.target.value);setEdited(true);}}/></label>
 <label>更正理由<textarea aria-label="更正理由" disabled={resource.busy||!!resource.retry} value={reason} onChange={e=>setReason(e.target.value)}/></label>
 <Button disabled={resource.busy||!!resource.retry||!boundedR6(edited?final:measure.final_text)||!boundedR6(reason)} onClick={()=>{const body={operation_key:crypto.randomUUID(),expected_material_version:measure.material_version,expected_measure_version:measure.current_version,final_text:edited?final:measure.final_text,reason};void resource.execute(async signal=>{await api.correctD5(capaId,measureId,body,signal);onChanged?.();});}}>提交更正</Button></>}
 </>}
 {resource.data&&resource.retry&&<Button disabled={resource.busy} onClick={()=>void resource.execute(resource.retry!.run)}>重试原请求</Button>}<p role="status">{resource.notice}</p>
 </Card>;
}
