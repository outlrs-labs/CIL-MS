import {useEffect,useMemo,useRef,useState} from 'react';
import {ArrowRight,BarChart3,Check,ChevronRight,Database,FileImage,FileSpreadsheet,FileText,Folder,FolderOpen,History,Search,Upload,X} from 'lucide-react';

export type AnalysisSource={version?:number;cadence?:string;period?:string;is_latest?:boolean;modified?:number;id:string;entity:string;family:string;name:string;relative_path:string;bytes:number;supported:boolean;extractable?:boolean;format?:string;extraction_id?:string};
export type AnalysisFolder={entity:string;family:string;name:string;cadences:string[]};
export type AnalysisCatalog={files:AnalysisSource[];folders:AnalysisFolder[];entities:string[];root_label?:string};
export type SavedAnalysis={id:string;title:string;status:string;phase?:string;progress?:number;document_progress?:number;document_index?:number;document_total?:number;current_page?:number;page_count?:number;current_source?:string|null;error?:string;period:string;scope_entities:string[];missing_entities:string[];sources:AnalysisSource[];target_entity:string;target_family:string;tables:unknown[]};
export type VersionSelection={family:string;version:number;cadence?:string;period?:string};

type Props={catalog:AnalysisCatalog|null;technical:boolean;entityCode:string;selected:Record<string,string>;setSelected:(value:Record<string,string>)=>void;entities:string[];setEntities:(value:string[])=>void;family:string;setFamily:(value:string)=>void;title:string;setTitle:(value:string)=>void;period:string;setPeriod:(value:string)=>void;target:string;setTarget:(value:string)=>void;targetFamily:string;setTargetFamily:(value:string)=>void;busy:boolean;generating?:boolean;online?:boolean;modelReady?:boolean;analyses:SavedAnalysis[];onCreate:(version?:VersionSelection)=>void;onGenerate?: (version?:VersionSelection)=>void;onOpen:(analysis:SavedAnalysis)=>void;onRefresh:()=>Promise<void>;token:string;workbenchMode?:boolean;openPickerSignal?:number};

const size=(value:number)=>value>=1024**2?(value/1024**2).toFixed(1)+' MB':Math.max(1,Math.ceil(value/1024))+' KB';

export function AnalysisDashboard({catalog,technical,entityCode,selected,setSelected,entities,setEntities,family,setFamily,title,setTitle,period,setPeriod,target,setTarget,targetFamily,setTargetFamily,busy,generating=false,online,modelReady,analyses,onCreate,onGenerate,onOpen,onRefresh,token,workbenchMode=false,openPickerSignal=0}:Props){
 const [picker,setPicker]=useState(false),[query,setQuery]=useState(''),[uploading,setUploading]=useState(false),[uploadError,setUploadError]=useState('');
 const [activeEntity,setActiveEntity]=useState(technical?'all':entityCode),[activeFamily,setActiveFamily]=useState(family);
 const [versionFamily,setVersionFamily]=useState(''),[versionKey,setVersionKey]=useState('');
  const [expanded,setExpanded]=useState<Set<string>>(()=>new Set(technical?[]:[entityCode]));
  const dialog=useRef<HTMLDialogElement>(null),folders=catalog?.folders||[],files=catalog?.files||[];
 const selectable=useMemo(()=>files.filter(file=>file.supported||file.extractable),[files]);
 const folderNames=useMemo(()=>new Map(folders.map(folder=>[folder.entity+'/'+folder.family,folder.name])),[folders]);
 const normalizedQuery=query.trim().toLocaleLowerCase();
 const visible=selectable.filter(file=>{
  const locationMatch=activeEntity==='all'||(file.entity===activeEntity&&(activeFamily==='all'||file.family===activeFamily));
  const haystack=[file.name,file.entity,file.family,folderNames.get(file.entity+'/'+file.family),file.period,file.cadence,file.relative_path].filter(Boolean).join(' ').toLocaleLowerCase();
  return normalizedQuery?haystack.includes(normalizedQuery):locationMatch;
 });
 const selectedFiles=files.filter(file=>file.id in selected);
 const selectedEntityFallback=technical?(catalog?.entities||[]):[entityCode];
 const uploadEntity=activeEntity==='all'?'':activeEntity;
 const canUpload=!!uploadEntity&&activeFamily!=='all';
  const activeFolder=folders.find(item=>item.entity===activeEntity&&item.family===activeFamily);
  const resultTitle=normalizedQuery?'Search results':activeEntity==='all'?(catalog?.root_label||'Data/cil'):activeFamily==='all'?activeEntity:(activeFolder?.name||activeFamily);
 const versionGroups=useMemo(()=>{
  const groups=new Map<string,{key:string;family:string;version:number;cadence?:string;period?:string;files:AnalysisSource[]}>();
  selectable.filter(file=>file.version!==undefined).forEach(file=>{
   const key=[file.family,file.cadence||'',file.period||'',file.version].join('|');
   const existing=groups.get(key);
   if(existing)existing.files.push(file);
   else groups.set(key,{key,family:file.family,version:file.version!,cadence:file.cadence,period:file.period,files:[file]});
  });
  return Array.from(groups.values()).sort((a,b)=>b.version-a.version||(b.period||'').localeCompare(a.period||'')||a.family.localeCompare(b.family));
 },[selectable]);
 const versionFamilies=useMemo(()=>Array.from(new Set(versionGroups.map(group=>group.family))),[versionGroups]);
 const chosenVersionFamily=versionFamily||versionFamilies[0]||'';
 const familyVersionGroups=versionGroups.filter(group=>group.family===chosenVersionFamily);
 const chosenVersion=familyVersionGroups.find(group=>group.key===versionKey)||familyVersionGroups[0];

	 function updateSelection(next:Record<string,string>){
	  setSelected(next);
	  const nextEntities=Array.from(new Set(files.filter(file=>file.id in next).map(file=>file.entity)));
	  setEntities(nextEntities.length?nextEntities:selectedEntityFallback);
	  if(technical){
	   if(nextEntities.length===1){
	    const first=files.find(file=>file.id in next);
	    setTarget(nextEntities[0]);
	    if(first)setTargetFamily(first.family);
	   }else setTarget('CMPDI');
	  }
	 }
 function showPicker(){setPicker(true);queueMicrotask(()=>dialog.current?.showModal());}
 const handledPickerSignal=useRef(openPickerSignal);
 useEffect(()=>{if(openPickerSignal!==handledPickerSignal.current){handledPickerSignal.current=openPickerSignal;showPicker();}},[openPickerSignal]);
 function closePicker(){dialog.current?.close();setPicker(false);}
 function selectLocation(entity:string,nextFamily='all'){
  setActiveEntity(entity);setActiveFamily(nextFamily);setFamily(nextFamily);
  if(entity!=='all')setExpanded(current=>new Set(current).add(entity));
 }
  function toggleExpanded(entity:string){setExpanded(current=>{const next=new Set(current);next.has(entity)?next.delete(entity):next.add(entity);return next;});}
  function count(entity?:string,nextFamily?:string){return selectable.filter(file=>(!entity||file.entity===entity)&&(!nextFamily||file.family===nextFamily)).length;}
 function chooseVersion(key:string){
  const group=versionGroups.find(item=>item.key===key);if(!group)return;
  setVersionKey(key);setVersionFamily(group.family);setFamily(group.family);setPeriod(group.period||'');
  // Subsidiary reports use the source family as their destination. CMPDI's
  // workbench keeps its technical destination; direct generation overrides it
  // safely in the parent using the selected source family.
  if(!technical)setTargetFamily(group.family);
  const next={...selected};group.files.forEach(file=>{next[file.id]='';});setSelected(next);
  setEntities(Array.from(new Set(group.files.map(file=>file.entity))));
  setTitle(`${folderNames.get(group.files[0].entity+'/'+group.family)||group.family.replaceAll('_',' ')} · v${group.version} report`);
 }
 async function uploadFiles(uploaded:FileList|null){
  if(!uploaded?.length||!canUpload)return;
  setUploading(true);setUploadError('');
  try{
   const added:Record<string,string>={...selected};
   for(const file of Array.from(uploaded)){
    const params=new URLSearchParams({entity:uploadEntity,family:activeFamily,name:file.name});
    const response=await fetch('/api/analytics/session-source?'+params,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},body:file});
    const data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'File could not be stored.');
    added[data.id]='';
   }
   await onRefresh();setSelected(added);setEntities(Array.from(new Set([...entities,uploadEntity])));
  }catch(error){setUploadError(error instanceof Error?error.message:'Upload failed.');}finally{setUploading(false);}
 }

	 return <div className={'analysis-dashboard '+(workbenchMode?'workbench-mode':'')}>
	  <section className="analysis-sourcebar panel">
	   <button className="button primary" onClick={showPicker}><FolderOpen size={17}/>{selectedFiles.length?'Change Files':'Choose Data'}</button>
	   {!workbenchMode&&<><div className="selected-source-preview">{selectedFiles.length?<>{selectedFiles.slice(0,3).map(file=><span key={file.id}><FileSpreadsheet size={14}/>{file.name}</span>)}{selectedFiles.length>3&&<small>+{selectedFiles.length-3}</small>}</>:<span className="empty-selection">No data selected</span>}</div>{!!selectedFiles.length&&<button className="text-button" onClick={()=>updateSelection({})}>Clear</button>}</>}
	   {workbenchMode&&!!selectedFiles.length&&<span className="workbench-selection-count">{selectedFiles.length} {selectedFiles.length===1?'file':'files'} selected</span>}
	   {workbenchMode&&<span className={'analytics-readiness '+(online===false?'offline':online?'ready':'checking')}><i/>{online===false?'Analytics unavailable':online&&modelReady===false?'Manual analysis ready · AI not configured':online?'Analytics ready':'Checking analytics…'}</span>}
	  </section>
	  {!workbenchMode&&<>
	  <section className="panel version-report-builder">
   <div className="section-heading"><div><h2><History size={18}/>Version report</h2><p>Select a report family and uploaded version. Every supported file in that version will be included automatically.</p></div><span className="subtle-pill">{versionGroups.length} version sets</span></div>
   {versionGroups.length?<>
    <div className="version-report-fields">
     <label className="field">Report family<select aria-label="Version report family" value={chosenVersionFamily} onChange={event=>{setVersionFamily(event.target.value);setVersionKey('');}}>{versionFamilies.map(item=><option key={item} value={item}>{folders.find(folder=>folder.family===item)?.name||item.replaceAll('_',' ')}</option>)}</select></label>
     <label className="field">Uploaded version<select aria-label="Uploaded report version" value={chosenVersion?.key||''} onChange={event=>chooseVersion(event.target.value)}>{familyVersionGroups.map(group=><option key={group.key} value={group.key}>v{group.version} · {group.cadence||'cycle'} · {group.period||'unspecified'} · {group.files.length} files</option>)}</select></label>
    </div>
    {chosenVersion&&<div className="version-report-summary"><div><strong>Version set ready</strong><span>{chosenVersion.files.length} files across {new Set(chosenVersion.files.map(file=>file.entity)).size} {new Set(chosenVersion.files.map(file=>file.entity)).size===1?'entity':'entities'} · v{chosenVersion.version}</span></div><div className="analytics-actions"><button className="button secondary" disabled={busy||generating||!online||!onCreate} onClick={()=>onCreate?.({family:chosenVersion.family,version:chosenVersion.version,cadence:chosenVersion.cadence,period:chosenVersion.period})}><BarChart3 size={15}/>Open workbench</button><button className="button primary" disabled={busy||generating||!onGenerate} onClick={()=>onGenerate?.({family:chosenVersion.family,version:chosenVersion.version,cadence:chosenVersion.cadence,period:chosenVersion.period})}>{generating?'Generating…':'Generate version report'}<ArrowRight size={16}/></button></div></div>}
   </>:<div className="empty small"><p>No uploaded versions are available yet. Upload a report package first.</p></div>}
  </section>
  <section className="panel analysis-launch">
   <div className="analysis-launch-fields"><label className="field">Analysis title<input value={title} maxLength={120} onChange={event=>setTitle(event.target.value)}/></label><label className="field">Period or project<input value={period} maxLength={120} onChange={event=>setPeriod(event.target.value)} placeholder="Optional"/></label></div>
   <details><summary>Report destination</summary><div className="analysis-launch-fields"><label className="field">Entity<select value={target} onChange={event=>{setTarget(event.target.value);setTargetFamily(event.target.value==='CMPDI'?'annual':'production_offtake');}}>{catalog?.entities.map(item=><option key={item}>{item}</option>)}</select></label><label className="field">Report family<select value={targetFamily} onChange={event=>setTargetFamily(event.target.value)}>{folders.filter(item=>item.entity===target).map(item=><option key={item.family} value={item.family}>{item.name}</option>)}</select></label></div></details>
   <div className="analysis-paths"><article><BarChart3/><span><strong>Analyze personally</strong><small>Open the selected files in the interactive workbench.</small></span><button className="button secondary" disabled={busy||generating||!online||!selectedFiles.length||title.trim().length<2} onClick={()=>onCreate?.()}>{busy?'Preparing…':'Open workbench'}<ArrowRight size={16}/></button></article><article><FileText/><span><strong>Generate report</strong><small>Create a ready-to-review summary with charts from every selected file.</small></span><button className="button primary" disabled={busy||generating||!selectedFiles.length||title.trim().length<2} onClick={()=>onGenerate?.()}>{generating?'Generating…':'Generate report'}<ArrowRight size={16}/></button></article></div>
  </section>
	  {!!analyses.length&&<section className="panel recent-analyses"><div className="section-heading"><h2><History size={18}/>Recent analyses</h2></div>{analyses.slice(0,5).map(item=><button key={item.id} disabled={busy} onClick={()=>onOpen(item)}><span><strong>{item.title}</strong><small>{item.sources.length} files · {item.status}</small></span><ArrowRight size={16}/></button>)}</section>}
	  </>}
  {picker&&<dialog ref={dialog} className="source-picker" aria-labelledby="source-picker-title" onCancel={event=>{event.preventDefault();closePicker();}}>
   <header><div><h2 id="source-picker-title">Choose data source</h2><p>Browse the approved CIL repository or search across its hierarchy.</p></div><button className="icon-button" aria-label="Close data selector" onClick={closePicker}><X size={20}/></button></header>
   <div className="source-picker-searchbar"><label className="source-search"><Search size={17}/><input aria-label="Search data hierarchy" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search files, folders, periods…"/>{query&&<button type="button" aria-label="Clear search" onClick={()=>setQuery('')}><X size={15}/></button>}</label><span aria-live="polite">{visible.length} {visible.length===1?'file':'files'}</span></div>
   {uploadError&&<p className="error source-picker-error" role="alert">{uploadError}</p>}
   <div className="source-browser">
    <nav className="source-hierarchy" aria-label="Data hierarchy">
     <button className={'source-node source-root '+(activeEntity==='all'&&!normalizedQuery?'active':'')} onClick={()=>selectLocation('all')}><Database size={18}/><span><strong>{catalog?.root_label||'Data/cil'}</strong><small>{count()} structured files</small></span></button>
     {catalog?.entities.map(entity=><div className="source-entity" key={entity}>
      <div className="source-entity-row"><button className={'source-node '+(activeEntity===entity&&activeFamily==='all'&&!normalizedQuery?'active':'')} onClick={()=>selectLocation(entity)}><Folder size={17}/><span><strong>{entity}</strong><small>{count(entity)} files</small></span></button><button className="source-disclosure" aria-label={(expanded.has(entity)?'Collapse ':'Expand ')+entity} aria-expanded={expanded.has(entity)} onClick={()=>toggleExpanded(entity)}><ChevronRight size={16}/></button></div>
      {expanded.has(entity)&&<div className="source-family-list">{folders.filter(folder=>folder.entity===entity).map(folder=><button key={folder.family} className={'source-family '+(activeEntity===entity&&activeFamily===folder.family&&!normalizedQuery?'active':'')} onClick={()=>selectLocation(entity,folder.family)}><span>{folder.name}</span><small>{count(entity,folder.family)}</small></button>)}</div>}
     </div>)}
    </nav>
    <section className="source-results" aria-label="Data files">
     <div className="source-results-heading"><div><span className="source-breadcrumb">{normalizedQuery?(catalog?.root_label||'Data/cil')+' / Search':activeEntity==='all'?'Repository':activeEntity+(activeFamily==='all'?'':' / '+(activeFolder?.name||activeFamily))}</span><h3>{resultTitle}</h3></div><label className={'button secondary device-upload '+(!canUpload?'disabled':'')} title={canUpload?'Add data or scanned documents to '+activeFolder?.name:'Choose an entity and report family to add files'} aria-disabled={!canUpload}><Upload size={16}/>{uploading?'Storing…':'Upload / OCR'}<input type="file" multiple accept=".csv,.xlsx,.json,.parquet,.pdf,.png,.jpg,.jpeg,.tif,.tiff" disabled={uploading||!canUpload} onChange={event=>void uploadFiles(event.target.files)}/></label></div>
     <div className="source-file-list">{visible.map(file=>{
      const checked=file.id in selected,folderName=folderNames.get(file.entity+'/'+file.family)||file.family;
      return <label key={file.id} className={'source-file-row '+(checked?'selected':'')}><input type="checkbox" checked={checked} onChange={()=>{const next={...selected};if(checked)delete next[file.id];else next[file.id]='';updateSelection(next);}}/><span className="source-file-icon">{file.extractable?(file.format==='pdf'?<FileText size={20}/>:<FileImage size={20}/>):<FileSpreadsheet size={20}/>}</span><span className="source-file-copy"><strong>{file.name}</strong><small>{file.entity} / {folderName}{file.period?' / '+file.period:''}</small></span><span className="source-file-meta">{file.version&&<small>v{file.version}{file.is_latest?' · Current':''}</small>}<small>{file.extractable?'OCR on open':file.cadence?file.cadence+' · '+size(file.bytes):size(file.bytes)}</small></span>{checked&&<Check className="source-check" size={16}/>}</label>;
     })}</div>
     {!visible.length&&<div className="source-empty"><FolderOpen size={28}/><strong>No matching structured files</strong><span>{normalizedQuery?'Try another name, entity, family, or period.':'Choose another folder in the data hierarchy.'}</span></div>}
    </section>
   </div>
	   <footer><span aria-live="polite"><strong>{Object.keys(selected).length}</strong> {Object.keys(selected).length===1?'file':'files'} selected</span><button className="button primary" disabled={!Object.keys(selected).length||busy||online!==true} onClick={()=>{closePicker();if(workbenchMode)onCreate();}}>Open selected data <ArrowRight size={16}/></button></footer>
  </dialog>}
 </div>;
}
