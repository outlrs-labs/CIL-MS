import {useEffect,useMemo,useState,type FormEvent} from 'react';
import {KeyRound,Plus,Trash2} from 'lucide-react';

type Provider={id:string;name:string;kind:string;models:string[];api_base:string;role?:'standard'|'primary'|'fallback';timeout_seconds?:number};
type ProviderHint={display:string;models:string;key:string;base:string};

const hints:Record<string,ProviderHint>={
 openai:{display:'CIL OpenAI server',models:'gpt-4.1-mini',key:'Paste the server-side OpenAI API key',base:'https://api.openai.com/v1 (optional)'},
 azure:{display:'CIL Azure OpenAI',models:'deployment-name',key:'Paste the Azure OpenAI key',base:'https://resource.openai.azure.com'},
 anthropic:{display:'CIL Anthropic',models:'claude-sonnet-4-5',key:'Paste the Anthropic API key',base:'Provider default (optional)'},
 gemini:{display:'Gemini fallback',models:'gemini-2.5-flash',key:'Paste the Gemini API key',base:'Provider default (optional)'},
 sarvam:{display:'Sarvam server primary',models:'sarvam-105b',key:'Paste the Sarvam API key',base:'https://api.sarvam.ai/v1 (managed automatically)'},
 ollama:{display:'Local Ollama',models:'qwen3:8b',key:'No key required for local Ollama',base:'http://localhost:11434'},
 compatible:{display:'CIL compatible gateway',models:'provider-model-id',key:'Paste the gateway API key',base:'https://your-provider.example/v1'},
};

export function ModelProviders({token,onChange}:{token:string;onChange:()=>void}){
 const [items,setItems]=useState<Provider[]>([]),[endpoint,setEndpoint]=useState('sarvam'),[name,setName]=useState(''),[models,setModels]=useState(''),[key,setKey]=useState(''),[base,setBase]=useState(''),[version,setVersion]=useState(''),[role,setRole]=useState<'standard'|'primary'|'fallback'>('primary'),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const hint=useMemo(()=>hints[endpoint],[endpoint]);
 async function load(){try{const r=await fetch('/api/cmpdi/providers',{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw new Error('Could not load model providers.');setItems(await r.json());}catch(e){setError(e instanceof Error?e.message:'Provider request failed.');}}
 useEffect(()=>{void load();},[token]);
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{const r=await fetch('/api/cmpdi/providers',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({name,endpoint,models:models.split(',').map(s=>s.trim()).filter(Boolean),api_key:key,api_base:base,api_version:version,role,timeout_seconds:role==='primary'?18:45})});const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Invalid provider settings.');setKey('');setName('');setModels('');await load();onChange();}catch(e){setError(e instanceof Error?e.message:'Provider save failed.');}finally{setBusy(false);}}
 async function remove(id:string){setBusy(true);setError('');try{const r=await fetch('/api/cmpdi/providers/'+id,{method:'DELETE',headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw new Error('Could not remove provider.');await load();onChange();}catch(e){setError(e instanceof Error?e.message:'Removal failed.');}finally{setBusy(false);}}
 function changeEndpoint(value:string){setEndpoint(value);setBase(value==='ollama'?'http://localhost:11434':'');setKey('');setVersion('');}
 return <section className="panel model-providers" aria-labelledby="model-provider-title">
  <div className="section-heading"><div><h2 id="model-provider-title"><KeyRound size={18}/>AI providers &amp; models</h2><p>Manage the shared server-side model connection used by Analyse.</p></div><span>{items.length} configured locally</span></div>
  <div className="analysis-setup">
   <p>The environment-backed server provider is the primary path. Gemini is tried only when that request fails before a response starts; locally added roles extend the same CIL Auto model.</p>
   {error&&<p className="error" role="alert">{error}</p>}
   {items.map(p=><div className="saved-analysis" key={p.id}><div><strong>{p.name}</strong><small>{p.role&&p.role!=='standard'?`${p.role} · `:''}{p.kind} · {p.models.join(', ')}</small></div><button className="text-button" disabled={busy} onClick={()=>void remove(p.id)}><Trash2 size={15}/>Remove</button></div>)}
   <form onSubmit={submit}>
    <div className="analysis-fields">
     <label className="field">Provider<select value={endpoint} onChange={e=>changeEndpoint(e.target.value)}><option value="sarvam">Sarvam AI</option><option value="gemini">Google Gemini</option><option value="openai">OpenAI</option><option value="azure">Azure OpenAI</option><option value="anthropic">Anthropic</option><option value="ollama">Ollama (local or remote)</option><option value="compatible">Third-party · OpenAI-compatible</option></select></label>
     <label className="field">Use as<select value={role} onChange={e=>setRole(e.target.value as typeof role)}><option value="standard">Standalone model</option><option value="primary">Primary · fast path</option><option value="fallback">Fallback · on failure</option></select><small>Use Gemini as fallback when the server provider should remain primary.</small></label>
     <label className="field">Display name<input required minLength={2} maxLength={70} value={name} onChange={e=>setName(e.target.value)} placeholder={hint.display}/></label>
     <label className="field">Model identifiers<input required value={models} onChange={e=>setModels(e.target.value)} placeholder={hint.models}/><small>Enter exact provider model IDs, separated by commas. Auto failover uses the first one.</small></label>
     <label className="field">API key {endpoint==='ollama'?'(optional)':''}<input type="password" required={endpoint!=='ollama'} autoComplete="new-password" value={key} onChange={e=>setKey(e.target.value)} placeholder={hint.key}/><small>Encrypted on the backend and never returned to the browser.</small></label>
     <label className="field">API base URL {['azure','compatible','ollama'].includes(endpoint)?'':'(optional)'}<input type="url" required={['azure','compatible','ollama'].includes(endpoint)} value={base} onChange={e=>setBase(e.target.value)} placeholder={hint.base}/></label>
     {endpoint==='azure'&&<label className="field">Azure API version<input required value={version} onChange={e=>setVersion(e.target.value)} placeholder="2024-10-21"/></label>}
    </div>
    <button className="button secondary" disabled={busy}><Plus size={16}/>{busy?'Saving…':'Add provider'}</button>
    <p>Open or reload an analysis to use the updated model route.</p>
   </form>
  </div>
 </section>;
}
