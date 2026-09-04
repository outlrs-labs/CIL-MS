import {useEffect,useId,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,ChevronRight,Download,RefreshCw,Search,SlidersHorizontal,X,FolderOpen,LoaderCircle} from 'lucide-react';

type Entry={name:string;path:string;kind:'file'|'folder';bytes:number|null;modified:number|null};
type ReportOption={id:string;name:string};
type Listing={path:string;entries:Entry[];total:number;next_offset:number|null;recursive:boolean;truncated:boolean;filter_options:{entities:string[];reports:Record<string,ReportOption[]>}};
const types=[['all','All items'],['folders','Folders'],['tables','Tables'],['documents','Documents'],['images','Images'],['archives','ZIP archives']];
const periods=[['0','Any time'],['1','Today'],['7','Last 7 days'],['30','Last 30 days'],['366','Last year']];
const sorts=[['name','Name A–Z'],['name_desc','Name Z–A'],['modified','Newest first'],['modified_asc','Oldest first']];
const size=(n:number|null)=>n===null?'':n<1024?n+' B':n<1024**2?(n/1024).toFixed(1)+' KB':n<1024**3?(n/1024**2).toFixed(1)+' MB':(n/1024**3).toFixed(1)+' GB';
const timestamp=(value:number|null)=>value?new Date(value*1000).toLocaleString('en-IN',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'';

function normalizeListing(value:unknown):Listing{
 if(!value||typeof value!=='object'||!Array.isArray((value as {entries?:unknown}).entries))throw Error('The Vault returned an invalid folder response. Refresh after restarting the backend.');
 const raw=value as Partial<Listing>,options=raw.filter_options;
 return {
  path:typeof raw.path==='string'?raw.path:'',entries:raw.entries as Entry[],total:typeof raw.total==='number'?raw.total:(raw.entries as Entry[]).length,
  next_offset:typeof raw.next_offset==='number'?raw.next_offset:null,recursive:Boolean(raw.recursive),truncated:Boolean(raw.truncated),
  filter_options:{entities:Array.isArray(options?.entities)?options.entities:[],reports:options?.reports&&typeof options.reports==='object'?options.reports:{}},
 };
}

function FolderIcon(){
 const id=useId().replaceAll(':','');
 return <svg className="vault-folder-icon" viewBox="0 0 120 100" aria-hidden="true"><defs><linearGradient id={id+'back'} x2="0" y2="1"><stop stopColor="var(--folder-back-start)"/><stop offset="1" stopColor="var(--folder-back-end)"/></linearGradient><linearGradient id={id+'front'} x2="0" y2="1"><stop stopColor="var(--folder-front-start)"/><stop offset="1" stopColor="var(--folder-front-end)"/></linearGradient></defs><path d="M3 23Q3 13 12 13H35Q39 13 43 18L49 22H108Q117 22 117 30V83Q117 92 108 92H12Q3 92 3 83Z" fill={'url(#'+id+'back)'}/><path d="M8 29Q8 25 13 25H108Q112 25 112 29V80H8Z" fill="var(--folder-paper)"/><path d="M3 37Q3 30 11 30H109Q117 30 117 37V84Q117 92 109 92H11Q3 92 3 84Z" fill={'url(#'+id+'front)'} stroke="var(--folder-stroke)" strokeWidth=".7"/><path d="M11 31H108" stroke="var(--folder-highlight)" strokeWidth="1.5"/></svg>;
}
function FileIcon({name}:{name:string}){
 const ext=name.split('.').pop()?.toUpperCase()||'FILE';
 return <svg className="vault-file-icon" viewBox="0 0 100 110" aria-hidden="true"><path d="M18 5H65L84 25V96Q84 104 76 104H18Q10 104 10 96V13Q10 5 18 5Z" fill="var(--file-paper)" stroke="var(--line)"/><path d="M65 5V20Q65 25 70 25H84" fill="var(--surface-alt)" stroke="var(--line)"/><path d="M25 39H68M25 48H68M25 57H58" stroke="#a2adb6" strokeWidth="2.5" strokeLinecap="round"/><rect x="21" y="70" width="52" height="20" rx="3" fill={ext==='PDF'?'#fee4e5':['CSV','XLSX','PARQUET'].includes(ext)?'#dcf3e8':'#e5eefb'}/><text x="47" y="84" textAnchor="middle" fill={ext==='PDF'?'#a82935':['CSV','XLSX','PARQUET'].includes(ext)?'#1b714a':'#375781'} fontSize={ext.length>5?8:10} fontWeight="600" fontFamily="inherit">{ext.slice(0,7)}</text></svg>;
}

export function VaultWorkspace({token,entityCode,canFilterSubsidiary}:{token:string;entityCode:string;canFilterSubsidiary:boolean}){
 const [history,setHistory]=useState(['']),[index,setIndex]=useState(0),[query,setQuery]=useState(''),[kind,setKind]=useState('all'),[days,setDays]=useState('0'),[sort,setSort]=useState('name'),[entityFilter,setEntityFilter]=useState(''),[reportFilter,setReportFilter]=useState(''),[filters,setFilters]=useState(false),[listing,setListing]=useState<Listing|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[selected,setSelected]=useState<Entry|null>(null),[downloading,setDownloading]=useState(false),[revision,setRevision]=useState(0),[offset,setOffset]=useState(0);
 const path=history[index],popover=useRef<HTMLDivElement>(null),filterButton=useRef<HTMLButtonElement>(null),grid=useRef<HTMLDivElement>(null),requestNumber=useRef(0);
 const filterCount=Number(Boolean(entityFilter))+Number(Boolean(reportFilter))+Number(kind!=='all')+Number(days!=='0')+Number(sort!=='name');
 const reportEntity=canFilterSubsidiary?entityFilter:entityCode;
 const reports=reportEntity?(listing?.filter_options?.reports?.[reportEntity]||[]):[];
 useEffect(()=>{
  const request=++requestNumber.current,controller=new AbortController();setLoading(true);setError('');
  const timer=setTimeout(async()=>{try{
   const params=new URLSearchParams({path,q:query,kind,days,sort,offset:String(offset)});if(entityFilter)params.set('entity',entityFilter);if(reportFilter)params.set('report',reportFilter);
   const r=await fetch('/api/analytics/vault?'+params,{headers:{Authorization:'Bearer '+token},signal:controller.signal});const raw=await r.json();
   if(!r.ok)throw Error(typeof raw.detail==='string'?raw.detail:'Could not open this folder.');const data=normalizeListing(raw);
   if(request===requestNumber.current)setListing(previous=>offset&&previous?{...data,entries:[...previous.entries,...data.entries]}:data);
  }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Could not open this folder.');}finally{if(request===requestNumber.current&&!controller.signal.aborted)setLoading(false);}},query?200:0);
  return()=>{clearTimeout(timer);controller.abort();};
 },[path,query,kind,days,sort,entityFilter,reportFilter,offset,revision,token]);
 useEffect(()=>{if(!filters)return;const click=(e:PointerEvent)=>{if(!popover.current?.contains(e.target as Node)&&!filterButton.current?.contains(e.target as Node))setFilters(false);};const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){setFilters(false);filterButton.current?.focus();}};document.addEventListener('pointerdown',click);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',click);document.removeEventListener('keydown',escape);};},[filters]);
 function resetView(){setQuery('');setOffset(0);setSelected(null);setListing(null);grid.current?.scrollTo({top:0});}
 function navigate(next:string){resetView();setHistory(old=>[...old.slice(0,index+1),next]);setIndex(index+1);}
 function travel(delta:number){resetView();setIndex(old=>old+delta);}
 function changeFilter(setter:(value:string)=>void,value:string){setter(value);setOffset(0);setSelected(null);}
 function resetToRoot(){setHistory(['']);setIndex(0);setOffset(0);setSelected(null);setListing(null);}
 function changeEntity(value:string){setEntityFilter(value);setReportFilter('');resetToRoot();}
 function changeReport(value:string){setReportFilter(value);resetToRoot();}
 function resetFilters(){setEntityFilter('');setReportFilter('');setKind('all');setDays('0');setSort('name');setOffset(0);setSelected(null);}
 async function download(entry:Entry){if(downloading)return;setDownloading(true);setError('');try{const r=await fetch('/api/analytics/vault/file?'+new URLSearchParams({path:entry.path}),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('File unavailable. Refresh the folder and try again.');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=entry.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){setError(e instanceof Error?e.message:'Download failed.');}finally{setDownloading(false);}}
 const crumbs=path.split('/').filter(Boolean),entries=listing?.entries||[];
 return <section className="vault-explorer" aria-label="Vault file explorer">
  <div className="vault-toolbar"><div className="vault-navigation"><button className="icon-button" aria-label="Back" disabled={index===0} onClick={()=>travel(-1)}><ArrowLeft size={18}/></button><button className="icon-button" aria-label="Forward" disabled={index===history.length-1} onClick={()=>travel(1)}><ArrowRight size={18}/></button><nav className="vault-breadcrumbs" aria-label="Folder path"><button onClick={()=>navigate('')} aria-current={!path?'page':undefined}>Data/cil</button>{crumbs.map((part,i)=><span key={i}><ChevronRight size={14}/><button aria-current={i===crumbs.length-1?'page':undefined} title={part} onClick={()=>navigate(crumbs.slice(0,i+1).join('/'))}>{part}</button></span>)}</nav></div>
   <div className="vault-tools"><label className="vault-search"><Search size={17}/><input aria-label="Search vault" placeholder="Search vault" value={query} onChange={e=>changeFilter(setQuery,e.target.value)}/>{query&&<button aria-label="Clear search" onClick={()=>changeFilter(setQuery,'')}><X size={14}/></button>}</label><div className="vault-filter-anchor"><button ref={filterButton} className={'button secondary vault-filter-button '+(filterCount?'is-filtered':'')} aria-expanded={filters} aria-controls="vault-filters" onClick={()=>setFilters(!filters)}><SlidersHorizontal size={16}/>Filter{filterCount>0&&<span>{filterCount}</span>}</button>{filters&&<div ref={popover} id="vault-filters" className="vault-filter-menu">
    {canFilterSubsidiary&&<label className="field">Subsidiary<select aria-label="Subsidiary" value={entityFilter} onChange={e=>changeEntity(e.target.value)}><option value="">All subsidiaries</option>{listing?.filter_options?.entities?.map(entity=><option key={entity} value={entity}>{entity}</option>)}</select></label>}
    <label className="field">Report<select aria-label="Report" value={reportFilter} disabled={!reportEntity} onChange={e=>changeReport(e.target.value)}><option value="">{reportEntity?'All reports':'Choose a subsidiary first'}</option>{reports.map(report=><option key={report.id} value={report.id}>{report.name}</option>)}</select></label>
    <label className="field">Type<select aria-label="File type" value={kind} onChange={e=>changeFilter(setKind,e.target.value)}>{types.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    <label className="field">Updated<select aria-label="Updated" value={days} onChange={e=>changeFilter(setDays,e.target.value)}>{periods.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    <label className="field">Sort by<select aria-label="Sort by" value={sort} onChange={e=>changeFilter(setSort,e.target.value)}>{sorts.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    <div><button className="text-button" onClick={resetFilters}>Reset</button><button className="button primary" onClick={()=>{setFilters(false);filterButton.current?.focus();}}>Done</button></div></div>}</div><button className="icon-button" aria-label="Refresh folder" disabled={loading} onClick={()=>{setOffset(0);setRevision(v=>v+1);}}><RefreshCw size={17} className={loading?'spin':''}/></button></div>
  </div>
  {filterCount>0&&<div className="vault-filter-chips">{entityFilter&&<button onClick={()=>changeEntity('')} aria-label="Remove subsidiary filter">{entityFilter}<X size={12}/></button>}{reportFilter&&<button onClick={()=>changeReport('')} aria-label="Remove report filter">{reports.find(item=>item.id===reportFilter)?.name||reportFilter}<X size={12}/></button>}{kind!=='all'&&<button onClick={()=>changeFilter(setKind,'all')} aria-label="Remove type filter">{types.find(item=>item[0]===kind)?.[1]}<X size={12}/></button>}{days!=='0'&&<button onClick={()=>changeFilter(setDays,'0')} aria-label="Remove date filter">{periods.find(item=>item[0]===days)?.[1]}<X size={12}/></button>}{sort!=='name'&&<button onClick={()=>changeFilter(setSort,'name')} aria-label="Reset sort">{sorts.find(item=>item[0]===sort)?.[1]}<X size={12}/></button>}</div>}
  {error&&<div className="error" role="alert">{error}<button className="text-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></div>}
  <div className="vault-grid" ref={grid} aria-busy={loading} aria-label="Folders and files">
   {(!loading||offset>0)&&!error&&entries.map(entry=><button key={entry.path} className={'vault-item '+(selected?.path===entry.path?'selected':'')} title={entry.name} aria-label={(entry.kind==='folder'?'Open folder ':'Select file ')+entry.name} aria-pressed={entry.kind==='file'?selected?.path===entry.path:undefined} onClick={()=>entry.kind==='folder'?navigate(entry.path):setSelected(entry)} onDoubleClick={()=>{if(entry.kind==='file')void download(entry);}}>{entry.kind==='folder'?<FolderIcon/>:<FileIcon name={entry.name}/>}<span>{entry.name}</span>{listing?.recursive&&<small>{entry.path.split('/').slice(0,-1).join('/')||'Data/cil'}</small>}{entry.kind==='file'&&entry.modified&&<time dateTime={new Date(entry.modified*1000).toISOString()}>{timestamp(entry.modified)}</time>}</button>)}
   {loading&&!offset&&<div className="vault-empty" role="status"><LoaderCircle className="spin" size={24}/><span>Loading…</span></div>}
   {!loading&&!error&&!entries.length&&<div className="vault-empty"><FolderOpen size={30}/><span>{query||filterCount?'No matches':'Empty folder'}</span>{Boolean(query||filterCount)&&<button className="text-button" onClick={()=>{setQuery('');resetFilters();}}>Clear filters</button>}</div>}
  </div>
  <footer className="vault-status"><span aria-live="polite">{selected?selected.name:listing?listing.total+' '+(listing.recursive?'results':'items'):''}{selected?.bytes!==null&&selected&&<small> · {size(selected.bytes)}</small>}{selected?.modified&&<small> · {timestamp(selected.modified)}</small>}</span>{selected&&<button className="text-button" disabled={downloading} onClick={()=>void download(selected)}>{downloading?<LoaderCircle size={15} className="spin"/>:<Download size={15}/>}Download</button>}{listing?.next_offset!==null&&listing?.next_offset!==undefined&&<button className="text-button" disabled={loading} onClick={()=>setOffset(listing.next_offset!)}>Load more</button>}</footer>
  {listing?.truncated&&<p className="vault-limit">Search limited. Open a folder to narrow results.</p>}
 </section>;
}
