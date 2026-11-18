import {useTranslation} from 'react-i18next';
import {useState} from 'react';
import {Button,Card} from 'antd';
import * as api from '../../api/capaR6';
import {useCapaCredentialIdentity} from './useCapaViewRequests';
import {useR6Resource} from './useR6Resource';
interface Props {capaId:string;kind:api.SourceKind;itemId:string;}
export default function CapaSourceDetails(props:Props){const {identity}=useCapaCredentialIdentity();return <Details key={identity+props.capaId+props.kind+props.itemId} {...props}/>;}
function Details({capaId,kind,itemId}:Props){
 const {t}=useTranslation('capa');
 const resource=useR6Resource(capaId,kind+itemId,signal=>api.getSourceDetails(capaId,kind,itemId,signal));
 const [evidence,setEvidence]=useState<{epoch:number;source:api.SourceDetail['sources'][number]}|null>(null);
 async function read(sourceId:string){const request=resource.requests.begin();try{const source=await api.readEvidence(capaId,kind,itemId,sourceId,request.signal);if(request.current())setEvidence({epoch:resource.cleared,source});}catch{if(request.current()){setEvidence(null);resource.refresh();}}finally{request.finish();}}
 return <Card size="small" title={t("r6.sourceTitle")}>
 <Button onClick={resource.refresh}>刷新依据</Button>
 {resource.data&&<><p>{resource.data.original_text}</p><p>证明状态：{String(resource.data.proof.state)} · {String(resource.data.proof.relation)}</p>
 {kind==='d4-candidate'&&<p>确认候选不签发验证或来源证明；请单独验证。</p>}
 {resource.data.sources.map(source=><section key={source.source_id}><p>{source.projection_id} · {source.version} · {source.current_state}</p><p>{source.fmea_id??source.snapshot_id} {source.node_id}</p>
 <Button aria-label={`重新核对来源 ${source.source_id}`} onClick={()=>void read(source.source_id)}>重新核对来源</Button>
 <pre>{source.evidence===null?'当前证据不可用；保留历史来源限制':JSON.stringify(source.evidence,null,2)}</pre></section>)}
 {evidence?.epoch===resource.cleared&&<pre>{JSON.stringify(evidence.source,null,2)}</pre>}
 </>}<p role="status">{resource.notice}</p></Card>;
}
