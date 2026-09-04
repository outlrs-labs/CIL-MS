import { createClient } from '@supabase/supabase-js';
const url = import.meta.env.VITE_SUPABASE_URL?.trim();
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();
export const configured = !!(url && key);
export const supabase = configured ? createClient(url,key,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:false}}) : null;
export const previewAvailable = import.meta.env.DEV && import.meta.env.VITE_ENABLE_UI_PREVIEW === 'true';
export async function api<T>(path:string, token:string, method='GET', body?:unknown):Promise<T> {
  const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${path}`,{
    method,headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},
    ...(body?{body:JSON.stringify(body)}:{})
  });
  const result=await response.json().catch(()=>null);
  if(!response.ok) throw new Error(typeof result?.detail==='string'?result.detail:'The request failed. Check your connection and try again.');
  return result as T;
}
