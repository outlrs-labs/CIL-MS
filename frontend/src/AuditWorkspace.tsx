import {useEffect,useState} from 'react';
import {Check,Clock3,Download,FileCheck2,RefreshCw,X,XCircle} from 'lucide-react';

type Audit={report_id:string;title:string;created:number;entity:string;status:string;comment:string;updated:number};
const statusLabel:Record<string,string>={
 pending_review:'Awaiting review',awaiting:'Awaiting information',rejected:'Rejected',
 submitted_to_cmpdi:'Submitted to CMPDI',assistant_manager_pending:'Awaiting review',
 manager_pending:'Awaiting review',changes_requested:'Rejected',approved:'Submitted to CMPDI'
};
const openStatuses=new Set(['pending_review','awaiting','assistant_manager_pending','manager_pending']);

export function AuditWorkspace({token,position='contributor',onChange}:{token:string;position?:string;onChange:()=>void}){
 const [items,setItems]=useState<Audit[]>([]),[selected,setSelected]=useState<Audit|null>(null);
 const [reportText,setReportText]=useState(''),[reportImage,setReportImage]=useState(''),[note,setNote]=useState('');
 const [loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const canReview=position==='manager';

 async function request(path:string,method='GET',body?:unknown){
  const response=await fetch('/api/analytics'+path,{method,headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'The audit request could not be completed.');return data;
 }
 async function refresh(){
  setError('');
  try{const next=await request('/audits');setItems(next);if(selected)setSelected(next.find((item:Audit)=>item.report_id===selected.report_id)||null)}
  catch(e){setError(e instanceof Error?e.message:'Could not load audit requests.')}
 }
 useEffect(()=>{void refresh()},[token]);
 useEffect(()=>{
  setReportText('');setReportImage('');setNote(selected?.comment||'');setError('');if(!selected)return;
  const controller=new AbortController();let imageUrl='';setLoading(true);
  async function load(){
   try{
    const options={headers:{Authorization:`Bearer ${token}`},signal:controller.signal};
    const textResponse=await fetch(`/api/analytics/reports/${selected!.report_id}/report.md`,options);
    if(!textResponse.ok)throw Error('The report preview is unavailable.');
    const text=await textResponse.text();if(!controller.signal.aborted)setReportText(text);
    const imageResponse=await fetch(`/api/analytics/reports/${selected!.report_id}/report.png`,options);
    if(imageResponse.ok){imageUrl=URL.createObjectURL(await imageResponse.blob());if(!controller.signal.aborted)setReportImage(imageUrl)}
   }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Could not open the report.')}
   finally{if(!controller.signal.aborted)setLoading(false)}
  }
  void load();return()=>{controller.abort();if(imageUrl)URL.revokeObjectURL(imageUrl)};
 },[selected?.report_id,token]);
 async function decide(decision:'approve'|'await'|'reject'){
  if(!selected)return;if(decision==='reject'&&!note.trim()){setError('Add a short reason before rejecting this report.');return}
  setBusy(true);setError('');
  try{const updated=await request(`/audits/${selected.report_id}/decision`,'POST',{decision,comment:note});setSelected(updated);await refresh();onChange()}
  catch(e){setError(e instanceof Error?e.message:'The decision could not be saved.')}finally{setBusy(false)}
 }
 async function download(){
  if(!selected)return;
  try{let response=await fetch(`/api/analytics/reports/${selected.report_id}/report.pdf`,{headers:{Authorization:`Bearer ${token}`}}),name=selected.title+'.pdf';if(!response.ok){response=await fetch(`/api/analytics/reports/${selected.report_id}/report.zip`,{headers:{Authorization:`Bearer ${token}`}});name=selected.title+'.zip'}if(!response.ok)throw Error('Report download is unavailable.');const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),10000)}
  catch(e){setError(e instanceof Error?e.message:'Download failed.')}
 }
 const pending=items.filter(item=>openStatuses.has(item.status)).length;
 return <section className="audit-simple">
  <header className="audit-simple-heading"><div><h2>File approval</h2><p>Reports for this subsidiary stay here until its manager approves them for CMPDI.</p></div><div><span>{pending} ongoing</span><button className="icon-button" aria-label="Refresh audit requests" onClick={()=>void refresh()}><RefreshCw size={17}/></button></div></header>
  {error&&!selected&&<p className="error" role="alert">{error}</p>}
  <div className={'audit-simple-layout '+(selected?'has-selection':'')}>
   <nav className="audit-request-list" aria-label="Audit requests">
    {items.map(item=><button key={item.report_id} className={selected?.report_id===item.report_id?'selected':''} onClick={()=>setSelected(item)}>
     <FileCheck2 size={20}/><span><strong>{item.title}</strong><small>{item.entity} · {new Date(item.created*1000).toLocaleDateString('en-IN')}</small></span><em data-status={item.status}>{statusLabel[item.status]||item.status.replaceAll('_',' ')}</em>
    </button>)}
    {!items.length&&<div className="audit-empty"><FileCheck2 size={30}/><strong>No audit requests</strong><span>Generate a report in Analyse, then send it for audit.</span></div>}
   </nav>
   {selected&&<article className="audit-request-preview">
    <header><div><h2>{selected.title}</h2><p>{selected.entity} · {statusLabel[selected.status]||selected.status}</p></div><button className="icon-button" aria-label="Close report" onClick={()=>setSelected(null)}><X size={18}/></button></header>
    <div className="audit-preview-body">{loading?<p role="status">Opening report…</p>:reportImage?<img src={reportImage} alt="Generated report preview"/>:<pre>{reportText}</pre>}</div>
    <footer>
     {error&&<p className="error" role="alert">{error}</p>}
     {openStatuses.has(selected.status)&&canReview?<><label className="field">Review note <span>Required only for rejection</span><textarea value={note} maxLength={1000} onChange={event=>setNote(event.target.value)} placeholder="Add a short note if needed"/></label><div className="audit-decisions"><button className="button audit-reject" disabled={busy||loading} onClick={()=>void decide('reject')}><XCircle size={17}/>Reject</button><button className="button secondary" disabled={busy||loading} onClick={()=>void decide('await')}><Clock3 size={17}/>Await</button><button className="button primary" disabled={busy||loading} onClick={()=>void decide('approve')}><Check size={17}/>Approve</button></div></>:<p className="audit-outcome">{selected.status==='submitted_to_cmpdi'?'Approved and submitted to CMPDI.':selected.status==='rejected'?'This report was rejected.':canReview?'This request is complete.':'Waiting for the subsidiary manager.'}</p>}
     <button className="text-button audit-download" onClick={()=>void download()}><Download size={15}/>Download report</button>
    </footer>
   </article>}
  </div>
 </section>
}
