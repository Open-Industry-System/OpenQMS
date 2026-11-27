import {useEffect,useRef,useState} from 'react';
import {useCapaChildRequests} from './useCapaViewRequests';
/** Current view ownership covers reads, mutations, retries and their reloads. */
export function useR6Resource<T>(report:string,selection:string,read:(signal:AbortSignal)=>Promise<T>){
 const requests=useCapaChildRequests(report,selection);
 const reader=useRef(read);reader.current=read;
 const fingerprint=useRef<{owner:typeof requests;value:string}|null>(null);
 const [snapshot,setSnapshot]=useState<{owner:typeof requests;value:T}|null>(null);
 const [revision,setRevision]=useState(0);
 const [cleared,setCleared]=useState(0);
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 const busyRef=useRef(false);
 type Operation=(signal:AbortSignal)=>Promise<unknown>;
 const [retry,setRetry]=useState<{run:Operation}|null>(null);
 const clear=()=>{setSnapshot(null);setRetry(null);setCleared(v=>v+1);};
 useEffect(()=>{clear();setNotice('');busyRef.current=false;setBusy(false);},[requests]);
 useEffect(()=>{
  const request=requests.begin();let timer:ReturnType<typeof setTimeout>;
  async function load(){try{const value=await reader.current(request.signal);if(request.current()){
    const next=JSON.stringify(value);
    const before=fingerprint.current;
    fingerprint.current={owner:requests,value:next};
    if(before?.owner===requests&&before.value!==next){
      setSnapshot(null);setCleared(v=>v+1);setNotice('材料已更新，请重新核对。');setRevision(v=>v+1);return;
    }
    setSnapshot({owner:requests,value});
  }}
  catch{if(request.current()){clear();setNotice('材料不可用，旧文本及版本已清除。');}}
  finally{if(request.current())timer=setTimeout(load,2000);}}
  void load();return()=>{clearTimeout(timer);request.cancel();};
 },[requests,revision]);
 async function execute(run:Operation){
  if(busyRef.current||snapshot?.owner!==requests)return;
  const request=requests.begin();if(!request.current())return;
  busyRef.current=true;setBusy(true);setNotice('提交中');
  try{await run(request.signal);if(request.current()){clear();setNotice('操作已确认');setRevision(v=>v+1);}}
  catch(error){if(!request.current())return;
   const status=(error as {response?:{status?:number}})?.response?.status;
   if(status&&[400,401,403,404,409,413,422].includes(status)){clear();setNotice('权限或材料已变化，请刷新后重新核对。');setRevision(v=>v+1);}
   else{setRetry({run});setNotice('操作尚未确认；重试发送原 key 和原参数。');}}
  finally{if(request.current()){busyRef.current=false;setBusy(false);}request.finish();}
 }
 return {data:snapshot?.owner===requests?snapshot.value:null,requests,cleared,busy,retry,notice,execute,
 refresh:()=>{requests.invalidate();clear();setRevision(v=>v+1);}};
}
export const boundedR6=(s:string)=>!!s.trim()&&new TextEncoder().encode(s).length<=16384;
