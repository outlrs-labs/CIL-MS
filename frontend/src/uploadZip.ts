export function uploadZip(file:File,query:URLSearchParams,token:string,onProgress:(value:number)=>void):Promise<{version:number;period:string;files:{status:string}[];pending_extraction:number}> {
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/analytics/submissions?'+query);
  xhr.setRequestHeader('Authorization',`Bearer ${token}`);xhr.setRequestHeader('Content-Type','application/zip');
  xhr.timeout=15*60*1000;
  xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100));};
  xhr.onerror=()=>reject(Error('Upload connection failed. Check submission history before retrying; the server may have received the ZIP.'));
  xhr.ontimeout=()=>reject(Error('Upload response timed out. Refresh version history before trying again.'));
  xhr.onload=()=>{
   let data;try{data=JSON.parse(xhr.responseText);}catch{reject(Error(`Upload failed (HTTP ${xhr.status}). Check that the backend is running.`));return;}
   if(xhr.status<200||xhr.status>=300){reject(Error(typeof data.detail==='string'?data.detail:'Upload could not be completed.'));return;}
   resolve(data);
  };
  xhr.send(file);
 });
}
