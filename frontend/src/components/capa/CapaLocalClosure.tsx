import {useTranslation} from 'react-i18next';
import {useEffect,useState} from 'react';
import {Button,Card} from 'antd';
import * as api from '../../api/capaR6';
import {getDocGateDecision,getDocGateAudit} from '../../api/capa';
import {useCapaCredentialIdentity} from './useCapaViewRequests';
import {boundedR6,useR6Resource} from './useR6Resource';
interface Props{capaId:string;status:string;onChanged?:()=>void;onEligibility?:(eligible:boolean|null)=>void;}
export default function CapaLocalClosure(props:Props){const {identity}=useCapaCredentialIdentity();return <Local key={identity+props.capaId+props.status} {...props}/>;}
function Local({capaId,status,onChanged,onEligibility}:Props){
 const {t}=useTranslation('capa');
 const resource=useR6Resource(capaId,status,async signal=>{
 const form=await api.getLocalClosure(capaId,signal);
 if(!form.eligible)return {form,catalog:null,decision:null,audits:[]};
 const catalog=status==='D8_GATE_PENDING'?await api.getManualCatalog(capaId,signal):null;
 if(catalog&&catalog.material_version!==form.material_version)throw new Error('Catalog changed');
 const manual=form.manual_analysis;
 const [decision,audit]=manual?await Promise.all([getDocGateDecision(capaId,signal),getDocGateAudit(capaId,signal)]):[null,{audits:[]}];
 return {form,catalog,decision,audits:audit.audits};});
 const [text,setText]=useState('');const [basis,setBasis]=useState('');const [reason,setReason]=useState('');
 const [manualReason,setManualReason]=useState('');const [docs,setDocs]=useState<Record<string,Record<string,unknown>>>({});
 const [empty,setEmpty]=useState(false);const [propagation,setPropagation]=useState('');
 const [deferReason,setDeferReason]=useState('');const [owner,setOwner]=useState('');const [deadline,setDeadline]=useState('');
 const [waiverReason,setWaiverReason]=useState('');const [waivers,setWaivers]=useState<Record<string,Record<string,unknown>>>({});
 useEffect(()=>{setText('');setBasis('');setReason('');setManualReason('');setDocs({});setEmpty(false);setPropagation('');setDeferReason('');setOwner('');setDeadline('');setWaiverReason('');setWaivers({});},[resource.cleared]);
 useEffect(()=>{onEligibility?.(resource.data?resource.data.form.eligible:null);},[resource.data?.form.eligible,onEligibility]);
 const data=resource.data;const form=data?.form;const editable=form?.can_edit===true;const disabled=resource.busy||!!resource.retry;
 const gate=status==='D8_GATE_PENDING';const analysis=form?.manual_analysis;
 function save(kind:'local-prevention'|'manual-doc-analysis'|'propagation-review',fields:Record<string,unknown>){if(!form)return;const body={operation_key:crypto.randomUUID(),expected_material_version:form.material_version,...fields};void resource.execute(async signal=>{await api.saveLocal(capaId,kind,body,signal);onChanged?.();});}
 function decide(action:'audit'|'confirm-no-affected'|'defer'|'waiver',fields:Record<string,unknown>={}){if(!form||!analysis?.analysis_id)return;const body={operation_key:crypto.randomUUID(),expected_material_version:form.material_version,expected_analysis_id:analysis.analysis_id,...fields};void resource.execute(signal=>api.manualDecision(capaId,action,body,signal));}
 if(form&&!form.eligible)return null;
 return <Card title={t("r6.localTitle")}>
 <Button disabled={disabled} onClick={resource.refresh}>刷新本地材料</Button>
 {form?.eligible&&<><p>来源限制继承自完整 Root、验证、正式 D5 和本地记录；空引用或零外部来源不解除限制。</p><p>本地表单版本 {form.material_version}</p>
 {(['prevention','manual_analysis','propagation'] as const).map(kind=>{const row=form[kind];return row&&<section key={kind}><h4>{kind} · 版本 {row.revision_no}</h4><p>{row.text}</p><p>{row.basis}</p><p>{row.reason}</p><pre>{JSON.stringify({sources:row.sources,report_snapshot_sources:row.report_snapshot_sources,channels:row.channels},null,2)}</pre></section>;})}
 {form.can_save_prevention&&<section><label>本地预防措施<textarea aria-label="本地预防措施" disabled={disabled} value={text} onChange={e=>setText(e.target.value)}/></label><label>本地预防依据<textarea aria-label="本地预防依据" disabled={disabled} value={basis} onChange={e=>setBasis(e.target.value)}/></label><label>本地预防理由<textarea aria-label="本地预防理由" disabled={disabled} value={reason} onChange={e=>setReason(e.target.value)}/></label><Button disabled={disabled||![text,basis,reason].every(boundedR6)} onClick={()=>save('local-prevention',{text,basis,reason})}>保存本地预防</Button></section>}
 {gate&&<section><h4>人工受影响文档分析</h4><p>逐项核对候选文档；未选择代表本轮空清单，保存后还需独立确认。</p>
 {(data?.catalog?.items??[]).map(candidate=><ManualDocument key={candidate.doc_id} candidate={candidate} disabled={!editable||disabled} onChange={value=>setDocs(old=>{const next={...old};if(value)next[candidate.doc_id]=value;else delete next[candidate.doc_id];return next;})}/>)}
 {form.can_save_manual_analysis&&<><label>人工分析理由<textarea aria-label="人工分析理由" disabled={disabled} value={manualReason} onChange={e=>setManualReason(e.target.value)}/></label><Button disabled={disabled||!form.prevention||!boundedR6(manualReason)||Object.values(docs).some(doc=>typeof doc.update_suggestion!=='string'||!boundedR6(doc.update_suggestion)||!Array.isArray(doc.key_points)||!doc.key_points.length)} onClick={()=>save('manual-doc-analysis',{reason:manualReason,affected_docs:Object.values(docs)})}>保存人工分析</Button></>}
 {analysis&&<><p>人工分析已记录；模型未运行，尚须独立门禁处置。</p><pre>{JSON.stringify(analysis.input_bindings.affected_docs,null,2)}</pre><p>门禁决定：{data?.decision?.decision??'尚未确认'}</p>
 {editable&&<><Button disabled={disabled} onClick={()=>decide('audit')}>运行文档审核</Button>
 {Array.isArray(analysis.input_bindings.affected_docs)&&analysis.input_bindings.affected_docs.length===0&&<><label><input aria-label="独立确认本轮无受影响文档" type="checkbox" disabled={disabled} checked={empty} onChange={e=>setEmpty(e.target.checked)}/>独立确认本轮无受影响文档</label><Button disabled={disabled||!empty} onClick={()=>decide('confirm-no-affected')}>确认空清单</Button></>}
 <h4>延期仍阻塞门禁</h4><label>延期理由<textarea aria-label="延期理由" disabled={disabled} value={deferReason} onChange={e=>setDeferReason(e.target.value)}/></label><label>负责人 ID<input aria-label="延期负责人" disabled={disabled} value={owner} onChange={e=>setOwner(e.target.value)}/></label><label>期限<input aria-label="延期期限" type="date" disabled={disabled} value={deadline} onChange={e=>setDeadline(e.target.value)}/></label><Button disabled={disabled||!boundedR6(deferReason)||!owner.trim()||!deadline} onClick={()=>decide('defer',{reason:deferReason,owner_id:owner,deadline})}>记录延期</Button></>}
 <pre>{JSON.stringify(data?.audits,null,2)}</pre>
 {form.can_waive&&<section><h4>仅对审核仍缺失的控制计划 modify 项目豁免</h4>
 {(data?.audits??[]).flatMap(audit=>(audit.coverage??[]).filter(point=>audit.doc_type==='control_plan'&&point.covered===false&&typeof point.key_point==='object'&&point.key_point!==null&&(point.key_point as Record<string,unknown>).expected_action==='modify'&&(point.key_point as Record<string,unknown>).target_kind==='cp_item').map(point=>{const kp=point.key_point as Record<string,unknown>;const item={doc_type:'control_plan',doc_id:audit.doc_id,target_key:String(kp.target_key??''),field:String(kp.field??'')};const key=JSON.stringify(item);return <label key={key}><input aria-label={`豁免 ${item.doc_id} ${item.target_key} ${item.field}`} type="checkbox" disabled={disabled} checked={!!waivers[key]} onChange={e=>setWaivers(old=>{const next={...old};if(e.target.checked)next[key]=item;else delete next[key];return next;})}/>{item.doc_id} {item.target_key} {item.field}</label>;}))}
 <label>豁免理由<textarea aria-label="豁免理由" disabled={disabled} value={waiverReason} onChange={e=>setWaiverReason(e.target.value)}/></label><Button disabled={disabled||!boundedR6(waiverReason)||!Object.keys(waivers).length} onClick={()=>decide('waiver',{reason:waiverReason,items:Object.values(waivers)})}>提交受限豁免</Button></section>}
 </>}
 </section>}
 {form.can_review_propagation&&<section><h4>传播本轮不执行</h4><p>lessons / knowledge / lateral / supplier_risk：NOT_EXECUTED</p><label>传播处置审阅理由<textarea aria-label="传播处置审阅理由" disabled={disabled} value={propagation} onChange={e=>setPropagation(e.target.value)}/></label><Button disabled={disabled||!form.prevention||!boundedR6(propagation)} onClick={()=>save('propagation-review',{reason:propagation})}>记录本轮不执行审阅</Button></section>}
 </>}
 {form&&resource.retry&&<Button disabled={resource.busy} onClick={()=>void resource.execute(resource.retry!.run)}>重试原请求</Button>}<p role="status">{resource.notice}</p>
 </Card>;
}
function ManualDocument({candidate,disabled,onChange}:{candidate:api.ManualCandidate;disabled:boolean;onChange:(value:Record<string,unknown>|null)=>void}){
 const [selected,setSelected]=useState(false);const [suggestion,setSuggestion]=useState('');const [action,setAction]=useState('modify');const [target,setTarget]=useState('');const [field,setField]=useState('');const [anchor,setAnchor]=useState('');const [business,setBusiness]=useState('');const [points,setPoints]=useState<Record<string,unknown>[]>([]);
 useEffect(()=>{onChange(selected?{doc_id:candidate.doc_id,doc_type:candidate.doc_type,update_suggestion:suggestion,key_points:points}:null);},[selected,suggestion,points]);
 const current=candidate.existing_targets.find(t=>t.target_key===target);
 const selectedAnchor=candidate.add_anchors.find(a=>JSON.stringify(a)===anchor);
 // Static command vocabulary, matching the server's strict add grammar. Source
 // coordinates still come exclusively from the currently authorized catalog.
 const addFields=candidate.doc_type==='fmea'?['prevention_control','detection_control','name']:['control_method','reaction_plan','special_class','sample_size','sample_frequency','product_characteristic','process_characteristic'];
 const valid=action==='document'||(action==='add'?selectedAnchor&&business.trim()&&addFields.includes(field):current&&current.allowed_fields.includes(field));
 return <section><label><input type="checkbox" aria-label={`选择受影响文档 ${candidate.doc_id}`} checked={selected} disabled={disabled} onChange={e=>setSelected(e.target.checked)}/>{candidate.doc_name} · {candidate.doc_id}</label>
 {selected&&<><label>更新建议<textarea aria-label={`更新建议 ${candidate.doc_id}`} disabled={disabled} value={suggestion} onChange={e=>setSuggestion(e.target.value)}/></label>
 <label>文档变更<select aria-label={`文档变更 ${candidate.doc_id}`} disabled={disabled} value={action} onChange={e=>{setAction(e.target.value);setField('');}}><option value="modify">修改</option><option value="delete">删除</option><option value="add">新增节点/项目</option>{candidate.baseline_version===null&&<option value="document">新增文档</option>}</select></label>
 {['modify','delete'].includes(action)&&<><select aria-label={`目标 ${candidate.doc_id}`} disabled={disabled} value={target} onChange={e=>{setTarget(e.target.value);setField('');}}><option value="">选择已知目标</option>{candidate.existing_targets.map(t=><option key={t.target_key} value={t.target_key}>{t.target_key}</option>)}</select><select aria-label={`字段 ${candidate.doc_id}`} disabled={disabled} value={field} onChange={e=>setField(e.target.value)}><option value="">选择字段</option>{current?.allowed_fields.map(f=><option key={f} value={f}>{f}</option>)}</select></>}
 {action==='add'&&<><select aria-label={`新增位置 ${candidate.doc_id}`} disabled={disabled} value={anchor} onChange={e=>setAnchor(e.target.value)}><option value="">选择已知位置</option>{candidate.add_anchors.map(a=><option key={JSON.stringify(a)} value={JSON.stringify(a)}>{a.parent_node_id} · {a.node_type}</option>)}</select><input aria-label={`业务标识 ${candidate.doc_id}`} disabled={disabled} value={business} onChange={e=>setBusiness(e.target.value)}/><select aria-label={`新增字段 ${candidate.doc_id}`} disabled={disabled} value={field} onChange={e=>setField(e.target.value)}><option value="">选择新增字段</option>{addFields.map(value=><option key={value} value={value}>{value}</option>)}</select></>}
 <Button disabled={disabled||!valid||points.length>=100} onClick={()=>{const point=action==='document'?{expected_action:'add',target_kind:'document'}:action==='add'?{expected_action:'add',target_kind:candidate.doc_type==='fmea'?'fmea_node':'cp_item',field,add_anchor:{...selectedAnchor,business_key:business}}:{expected_action:action,target_kind:candidate.doc_type==='fmea'?'fmea_node':'cp_item',target_key:target,field};setPoints(old=>[...old,point]);}}>添加核对点</Button>
 <pre>{JSON.stringify(points,null,2)}</pre><Button disabled={disabled} onClick={()=>setPoints([])}>清空核对点</Button></>}
 </section>;
}
