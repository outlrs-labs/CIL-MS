import { createClient } from '@supabase/supabase-js';
const url = import.meta.env.VITE_SUPABASE_URL?.trim();
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();
export const configured = !!(url && key);
export const supabase = configured ? createClient(url,key,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:false}}) : null;
export const previewAvailable = import.meta.env.DEV && import.meta.env.VITE_ENABLE_UI_PREVIEW === 'true';
export async function api<T>(path:string, token:string, method='GET', body?:unknown):Promise<T> {
  // Keep browser requests same-origin by default. In development Vite forwards
  // /api to FastAPI; in deployment the reverse proxy does the same. This avoids
  // loopback hostname/CORS mismatches between localhost and 127.0.0.1.
  const localBrowser=typeof window!=='undefined'&&['localhost','127.0.0.1'].includes(window.location.hostname);
  const base=localBrowser?'':(import.meta.env.VITE_API_URL || '').replace(/\/$/,'');
  const response = await fetch(`${base}${path}`,{
    method,headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},
    ...(body?{body:JSON.stringify(body)}:{})
  });
  const result=await response.json().catch(()=>null);
  if(!response.ok) throw new Error(typeof result?.detail==='string'?result.detail:'The request failed. Check your connection and try again.');
  return result as T;
}
