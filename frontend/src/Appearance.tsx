import {useEffect,useState} from 'react';
import {Check,Sun,Moon,Palette} from 'lucide-react';

export const accents=[
 {id:'blue',name:'IBM Blue',color:'#0f62fe',description:'Carbon Blue 60'},
 {id:'purple',name:'Purple',color:'#8a3ffc',description:'Carbon Purple 60'},
 {id:'green',name:'Green',color:'#198038',description:'Carbon Green 60'},
 {id:'magenta',name:'Magenta',color:'#d02670',description:'Carbon Magenta 60'},
 {id:'teal',name:'Teal',color:'#007d79',description:'Carbon Teal 60'},
] as const;
type Accent=typeof accents[number]['id'];
type Preferences={mode:'light'|'dark';accent:Accent};
const key='cil.appearance.v1';
function read():Preferences {
 try {const saved=JSON.parse(window.localStorage.getItem(key)||'{}');return {mode:saved.mode==='dark'?'dark':'light',accent:accents.some(a=>a.id===saved.accent)?saved.accent:'green'};} catch {return {mode:'light',accent:'green'};}
}
export function useAppearance(){
 const [preferences,setPreferences]=useState<Preferences>(read);
 useEffect(()=>{
  document.documentElement.dataset.theme=preferences.mode;
  document.documentElement.dataset.accent=preferences.accent;
  document.documentElement.style.setProperty('--accent-base',accents.find(a=>a.id===preferences.accent)!.color);
  try{window.localStorage.setItem(key,JSON.stringify(preferences));}catch{/* Theme changes still work when device storage is unavailable. */}
 },[preferences]);
 return {preferences,setPreferences};
}
export function Appearance({preferences,onChange}:{preferences:Preferences;onChange:(value:Preferences)=>void}){
 return <section className="appearance-settings" aria-labelledby="appearance-title">
  <h2 id="appearance-title">Appearance</h2><p>Theme and accent, saved on this device.</p>
  <fieldset><legend><Sun size={18}/> Mode</legend><div className="mode-options">
   {(['light','dark'] as const).map(mode=>{const Icon=mode==='light'?Sun:Moon;return <button key={mode} className="mode-card" aria-pressed={preferences.mode===mode} onClick={()=>onChange({...preferences,mode})}><span className="mode-icon"><Icon size={22}/></span><strong>{mode==='light'?'Light':'Dark'}</strong>{preferences.mode===mode&&<span className="active-label"><Check size={14}/>Active</span>}</button>;})}
  </div></fieldset>
  <fieldset><legend><Palette size={18}/> Accent color</legend><div className="accent-options">
   {accents.map(accent=><button key={accent.id} className="accent-card" aria-pressed={preferences.accent===accent.id} onClick={()=>onChange({...preferences,accent:accent.id})} style={{'--swatch':accent.color} as React.CSSProperties}><div className="accent-card-top"><span className="color-swatch"/>{preferences.accent===accent.id&&<span className="active-label"><Check size={14}/>Active</span>}</div><strong>{accent.name}</strong><p>{accent.description}</p><span className="color-strip"><i/><i/><i/></span></button>)}
  </div></fieldset>

 </section>;
}
