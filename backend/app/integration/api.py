"""CMPDI-only adapter. Upstream is private; browser identity/path headers are never forwarded."""
import asyncio
import base64
import csv
import hashlib
import json
import secrets
import re
import zipfile
import os
import shutil
import time
import tempfile
import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote
from uuid import UUID, uuid4
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from ..auth import Principal, member, principal, gateway
from ..config import settings
from .repository import Repository, PRODUCTION, TECHNICAL, ENTITIES, OPERATING, FORMATS, OCR_FORMATS, atomic_json

from . import submissions,ocr
from . import vault
from . import quick_report
from .report_templates import analyst_instructions
router=APIRouter()
logger=logging.getLogger(__name__)
@lru_cache
def repository():
 c=settings();r=Repository(c.cil_data_root,c.cil_processing_root);r.initialize();submissions.initialize(r);submissions.publish_schedule(r);return r
async def cmpdi(p:Principal=Depends(member)):
 if p.profile['role']!='cmpdi':raise HTTPException(403,'Only CMPDI can use the analytics workbench.')
 return p

async def analyst(p:Principal=Depends(member)):
 if p.profile['role'] not in ('cmpdi','subsidiary'):raise HTTPException(403,'Only CMPDI and production subsidiaries can use analytics.')
 if p.profile['role']=='subsidiary' and p.entity.get('code') not in OPERATING:raise HTTPException(403,'Invalid production subsidiary assignment.')
 return p

def entity_scope(p):return p.entity['code'] if p.profile['role']=='subsidiary' else None

def owned_analysis(id,p):
 a=repository().get_analysis(id,p.id)
 code=entity_scope(p)
 if code and (a.get('target_entity')!=code or set(a.get('scope_entities',[]))!={code}):raise HTTPException(403,'Analysis is outside your subsidiary.')
 return a

def headers(owner,id):
 secret=settings().df_bridge_secret.get_secret_value()
 if not secret:raise HTTPException(503,'Analytics bridge is not configured.')
 return {'X-CIL-Bridge':secret,'X-CIL-User':owner+'_'+id,'X-Workspace-Id':id}
async def upstream(owner,id,path,method='GET',payload=None):
 attempts=3 if method=='GET' else 1
 for attempt in range(attempts):
  try:
   async with httpx.AsyncClient(timeout=180) as c:
    r=await c.request(method,settings().df_url+path,headers=headers(owner,id),json=payload)
   if r.status_code==422:
    try:detail=r.json().get('error',{}).get('message','Source table could not be imported.')
    except ValueError:detail='Source table could not be imported.'
    raise HTTPException(422,detail)
   if r.status_code in (502,503,504) and attempt+1<attempts:
    await asyncio.sleep(.2*(attempt+1));continue
   if not r.is_success:
    logger.warning('Analytics upstream rejected %s %s with status %s',method,path,r.status_code)
    if r.status_code==403:raise HTTPException(503,'The analytics bridge needs a restart. Restart the local workspace and try again.')
    raise HTTPException(503,'The analytics engine is temporarily unavailable. Try again after the workspace finishes starting.')
   try:result=r.json()
   except ValueError:
    logger.warning('Analytics upstream returned a non-JSON response for %s %s',method,path)
    raise HTTPException(503,'The analytics engine returned an invalid response. Restart the local workspace.') from None
   if result.get('status')=='error':raise HTTPException(422,result.get('error',{}).get('message','Analysis operation failed.'))
   return result.get('data',result)
  except httpx.RequestError:
   if attempt+1<attempts:
    await asyncio.sleep(.2*(attempt+1));continue
   logger.warning('Analytics upstream is unreachable for %s %s',method,path)
 raise HTTPException(503,'The local analytics engine is offline. Start the complete workspace and retry.') from None

class InputSelection(BaseModel):
 model_config=ConfigDict(extra='forbid')
 file_id:str
 sheet:str|None=None
class AnalysisInput(BaseModel):
 model_config=ConfigDict(extra='forbid')
 title:str=Field(min_length=2,max_length=120)
 inputs:list[InputSelection]=Field(min_length=1,max_length=100)
 period:str=Field(default='',max_length=120)
 scope_entities:list[str]=Field(default_factory=lambda:list(OPERATING))
 target_entity:str='CMPDI'
 target_family:str='annual'
class AuditDecision(BaseModel):
 model_config=ConfigDict(extra='forbid')
 decision:str=Field(pattern='^(approve|await|reject)$')
 comment:str=Field(default='',max_length=1000)
class AuditSubmission(BaseModel):
 model_config=ConfigDict(extra='forbid')
 category:str=Field(pattern='^(production_offtake|environmental_compliance|financial|operational_statistics|washery_operations)$')
class QuickReportInput(AnalysisInput):
 send_for_audit:bool=False
 # Version-report metadata. When present, the server resolves the complete
 # version set from the catalog instead of trusting a partial client list.
 source_family:str|None=None
 source_cadence:str|None=None
 source_period:str|None=None
 source_version:int|None=Field(default=None,ge=1)

jobs:set[asyncio.Task]=set()
async def import_analysis(value,selection):
 repo=repository()
 try:
  resolved=[];document_context=[];documents=[entry for entry,_ in selection if entry.get('extractable')];document_index=0
  for entry,inp in selection:
   if entry.get('extractable'):
    index=document_index;document_index+=1
    value.update(phase='extracting',current_source=entry['name'],document_index=index+1,document_total=len(documents),progress=round(index/max(len(documents),1)*90));repo.put_analysis(value)
    def extraction_progress(current):
     page_progress=max(0,min(100,int(current.get('progress') or 0)))
     overall=round((index+page_progress/100)/max(len(documents),1)*90)
     value.update(progress=overall,document_progress=page_progress,current_page=current.get('current_page'),page_count=current.get('page_count'));repo.put_analysis(value)
    job=await ocr.ensure_for_analysis(repo,entry,value['owner'],extraction_progress)
    derivatives=[item for item in ocr.catalog_files(repo,entry['entity'],True) if item.get('extraction_id')==job['id'] and item.get('supported')]
    if not derivatives:raise HTTPException(422,f'No Markdown or CSV data could be extracted from {entry["name"]}.')
    resolved.extend((item,InputSelection(file_id=item['id'])) for item in derivatives)
    document_context.append({'source':entry['name'],'extraction_id':job['id'],'outputs':[item['name'] for item in derivatives]})
   else:resolved.append((entry,inp))
  value.update(phase='importing',progress=94,document_progress=100,document_context=document_context);repo.put_analysis(value)
  captured=[];snapshots={}
  for entry,inp in resolved:
   if entry['id'] not in snapshots:snapshots[entry['id']]=await asyncio.to_thread(repo.snapshot,entry,value['id'])
   captured.append({**snapshots[entry['id']],'sheet':inp.sheet})
  value['sources']=captured;repo.put_analysis(value)
  data=await upstream(value['owner'],value['id'],'/cil/import','POST',{'sources':captured,'title':value['title'],'period':value['period']})
  value.update(status='ready',phase='ready',progress=100,current_source=None,tables=data['tables'],error=None)
 except asyncio.CancelledError:
  value.update(status='failed',error='Import interrupted by a server restart. Create a new analysis.')
  raise
 except Exception as exc:
  value.update(status='failed',error=exc.detail if isinstance(exc,HTTPException) else 'Input capture or import failed. Check the file format, sheet name and local service log.')
 finally:repo.put_analysis(value)

@router.get('/api/cmpdi/catalog')
async def catalog(include_history:bool=False,p:Principal=Depends(analyst)):
 return await asyncio.to_thread(submissions.versioned_catalog,repository(),entity_scope(p),include_history)

@router.post('/api/cmpdi/session-source',status_code=201)
async def session_source(request:Request,entity:str=Query(max_length=16),family:str=Query(max_length=64),name:str=Query(max_length=180),p:Principal=Depends(analyst)):
 repo=repository();code=entity_scope(p)
 if code and entity!=code:raise HTTPException(403,'Choose your assigned subsidiary.')
 if entity not in ENTITIES:raise HTTPException(422,'Choose a valid subsidiary.')
 families=TECHNICAL if entity=='CMPDI' else PRODUCTION
 if family not in families:raise HTTPException(422,'Choose a valid report family.')
 filename=unquote(name).strip()
 if not filename or filename!=Path(filename).name or filename.startswith('.') or '/' in filename or '\\' in filename:raise HTTPException(422,'Invalid file name.')
 suffix=Path(filename).suffix.lower()
 if suffix not in FORMATS|OCR_FORMATS:raise HTTPException(422,'Use CSV, XLSX, JSON, Parquet, PDF, PNG, JPEG or TIFF.')
 body=await bounded_body(request,256*1024**2)
 if not body:raise HTTPException(422,'Choose a non-empty file.')
 destination=repo.root/entity/family/'data'/'analysis_uploads'/str(uuid4())/filename
 if not destination.resolve().is_relative_to(repo.root) or any(x.is_symlink() for x in [destination,*destination.parents]):raise HTTPException(403,'Unsafe storage destination.')
 destination.parent.mkdir(parents=True,exist_ok=False)
 try:
  temporary=destination.with_suffix(destination.suffix+'.part');temporary.write_bytes(body);os.replace(temporary,destination)
 except BaseException:
  shutil.rmtree(destination.parent,ignore_errors=True);raise
 relative=destination.relative_to(repo.root).as_posix();stat=destination.stat()
 fingerprint=f'{relative}:{stat.st_size}:{stat.st_mtime_ns}'
 return {'id':hashlib.sha256(fingerprint.encode()).hexdigest(),'entity':entity,'family':family,'name':filename,'relative_path':relative,'bytes':stat.st_size,'modified':stat.st_mtime,'supported':suffix in FORMATS,'extractable':suffix in OCR_FORMATS,'format':suffix.lstrip('.'),'session_upload':True}
@router.get('/api/cmpdi/status')
async def status(p:Principal=Depends(analyst)):
 try:
  value=await upstream(p.id,'status','/cil/health')
  return {'online':True,'model_ready':bool(value.get('models')),**value}
 except HTTPException as exc:return {'online':False,'model_ready':False,'models':[],'message':exc.detail}
@router.post('/api/cmpdi/analyses',status_code=202)
async def create_analysis(data:AnalysisInput,p:Principal=Depends(analyst)):
 repo=repository();items={e['id']:e for e in (await asyncio.to_thread(submissions.versioned_catalog,repo,entity_scope(p),True))['files']}
 code=entity_scope(p)
 if code and (data.target_entity!=code or set(data.scope_entities)!={code}):raise HTTPException(403,'Select only your own subsidiary and report destination.')
 families=TECHNICAL if data.target_entity=='CMPDI' else PRODUCTION
 if data.target_entity not in ENTITIES or data.target_family not in families:raise HTTPException(422,'Choose a valid report destination.')
 if not data.scope_entities or not set(data.scope_entities)<=set(ENTITIES):raise HTTPException(422,'Choose valid subsidiaries.')
 selected=[];seen=set();versions={}
 for inp in data.inputs:
  entry=items.get(inp.file_id)
  if not entry or not (entry.get('supported') or entry.get('extractable')):raise HTTPException(422,'A selected input is missing, changed or unsupported. Refresh the catalog.')
  if entry['entity'] not in data.scope_entities:raise HTTPException(422,'Selected file is outside the requested subsidiary scope.')
  if entry.get('submission_id'):
   group=(entry['entity'],entry['family'],entry['cadence'],entry['period'])
   if group in versions and versions[group]!=entry['submission_id']:raise HTTPException(422,'Do not mix revisions of the same reporting period in one analysis.')
   versions[group]=entry['submission_id']
  key=(inp.file_id,inp.sheet)
  if key in seen:raise HTTPException(422,'Duplicate file/sheet selection.')
  seen.add(key);selected.append((entry,inp))
 await upstream(p.id,'status','/cil/health')
 value={'id':str(uuid4()),'owner':p.id,'title':data.title,'period':data.period,'target_entity':data.target_entity,'target_family':data.target_family,'scope_entities':data.scope_entities,'missing_entities':sorted(set(data.scope_entities)-{e['entity'] for e,_ in selected}),'created':time.time(),'status':'importing','phase':'queued','progress':0,'sources':[],'document_context':[],'tables':[]}
 repo.put_analysis(value)
 task=asyncio.create_task(import_analysis(value,selected));jobs.add(task);task.add_done_callback(jobs.discard)
 return value
@router.get('/api/cmpdi/analyses')
async def analyses(p:Principal=Depends(analyst)):
 items=repository().list_analyses(p.id);code=entity_scope(p)
 return [a for a in items if not code or (a.get('target_entity')==code and set(a.get('scope_entities',[]))=={code})]
@router.get('/api/cmpdi/analyses/{id}')
async def analysis(id:UUID,p:Principal=Depends(analyst)):return owned_analysis(str(id),p)

# Workbench credentials stay in memory so bearer tokens are never written to disk.
# The portal renews this cookie in the background while an analysis is active.
WORKBENCH_SESSION_SECONDS=8*60*60
sessions={}
@router.post('/api/cmpdi/analyses/{id}/workbench-session')
async def open_workbench(id:UUID,response:Response,p:Principal=Depends(analyst)):
 a=owned_analysis(str(id),p)
 if a['status']!='ready':raise HTTPException(409,'Analysis is not ready.')
 for key,value in list(sessions.items()):
  if value['expires']<time.time():sessions.pop(key,None)
 key=secrets.token_urlsafe(32);sessions[hashlib.sha256(key.encode()).hexdigest()]={'token':p.token,'owner':p.id,'analysis':str(id),'expires':time.time()+WORKBENCH_SESSION_SECONDS}
 base=f'/cmpdi/workbench/{id}/'
 response.set_cookie('cil_workbench',key,max_age=WORKBENCH_SESSION_SECONDS,httponly=True,secure=settings().workbench_cookie_secure,samesite='strict',path=base)
 return {'url':base,'expires_in':WORKBENCH_SESSION_SECONDS}

async def bounded_body(request:Request,limit:int):
 chunks=[];size=0
 async for chunk in request.stream():
  size+=len(chunk)
  if size>limit:raise HTTPException(413,'Payload exceeds the local export limit.')
  chunks.append(chunk)
 return b''.join(chunks)

async def workbench_principal(request:Request,id:UUID):
 key=request.cookies.get('cil_workbench','');session_key=hashlib.sha256(key.encode()).hexdigest();s=sessions.get(session_key)
 if not s or s['expires']<time.time() or s['analysis']!=str(id):
  sessions.pop(session_key,None)
  raise HTTPException(401,'Reopen this analysis from your portal to renew the workbench session.')
 if request.method not in ('GET','HEAD'):
  origin=request.headers.get('origin')
  if origin not in settings().origins:raise HTTPException(403,'Untrusted workbench origin.')
 p=await principal(HTTPAuthorizationCredentials(scheme='Bearer',credentials=s['token']),gateway(request))
 p=await member(p);await analyst(p)
 if p.id!=s['owner']:raise HTTPException(403,'Invalid workbench identity.')
 owned_analysis(str(id),p)
 s['expires']=time.time()+WORKBENCH_SESSION_SECONDS
 return p

# Intentionally narrow; no connector, file upload, credential, local desktop, reset, migration or arbitrary SQL endpoints.
READ={'api/app-config','api/auth/info','api/sessions/list','api/tables/list-tables','api/tables/get-table','api/agent/list-global-models'}
WRITE={'api/sessions/load','api/sessions/save','api/sessions/update-meta','api/tables/sample-table','api/tables/analyze','api/tables/export-table-csv','api/agent/analyst-streaming','api/agent/data-operation-preview','api/agent/refresh-derived-data','api/agent/nl-to-filter','api/agent/chart-restyle','api/agent/sort-data','api/agent/derive-starter-questions','api/agent/process-data-on-load','api/agent/code-expl','api/agent/classify-chart-intent','api/agent/check-available-models','api/agent/list-global-models','api/agent/workspace-name','api/agent/test-model'}

@router.api_route('/cmpdi/workbench/{id}/{path:path}',methods=['GET','POST'])
async def workbench(id:UUID,path:str,request:Request):
 p=await workbench_principal(request,id);sid=str(id);repo=repository();a=owned_analysis(sid,p)
 if path=='cil/save-report' and request.method=='POST':return await save_report(request,p,a)
 if path=='cil/context' and request.method=='GET':return {'id':sid,'title':a['title'],'period':a['period'],'target_entity':a['target_entity'],'target_family':a['target_family'],'sources':a['sources']}
 if path=='api/connectors' and request.method=='GET':return {'status':'ok','data':{'connectors':[]}}
 if path.startswith('api/'):
  allowed=READ if request.method=='GET' else WRITE
  if path not in allowed:raise HTTPException(403,'This capability is not enabled in the analytics workbench.')
  payload=None
  if request.method=='POST':
   body=await bounded_body(request,25*1024*1024)
   try:payload=json.loads(body or b'{}')
   except ValueError:raise HTTPException(422,'Invalid JSON.')
   if path.startswith('api/sessions/'):
    if payload.get('id',sid)!=sid:raise HTTPException(403,'Workspace mismatch.')
    payload['id']=sid
   if path=='api/agent/analyst-streaming':
    payload['agent_exploration_rules']='Use ONLY the selected workspace tables. Sources are unvalidated local data. Disclose missing data and uncertainty. Never sum daily records together with monthly summaries. Compute numerical facts on full tables; do not infer totals from samples. Include units and periods. Report scope: '+json.dumps({'period':a['period'],'entities':a['scope_entities'],'missing':a['missing_entities']})+analyst_instructions(a['target_entity'],a['target_family'])
  params=dict(request.query_params)
  if path=='api/sessions/list':params={}
  client=httpx.AsyncClient(timeout=httpx.Timeout(240,connect=10))
  try:
   upstream_request=client.build_request(request.method,settings().df_url+'/'+path,headers=headers(p.id,sid),json=payload,params=params)
   result=await client.send(upstream_request,stream=True)
  except httpx.RequestError:
   await client.aclose();raise HTTPException(503,'The local analytics engine is unavailable.') from None
  async def stream():
   try:
    async for chunk in result.aiter_bytes():yield chunk
   finally:await result.aclose();await client.aclose()
  return StreamingResponse(stream(),status_code=result.status_code,media_type=result.headers.get('content-type','application/json'),headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
 # Static bundle and SPA. Assets contain no source data but still require the workbench session.
 dist=Path(__file__).resolve().parents[3]/'data-analyser'/'py-src'/'data_formulator'/'dist'
 if not path or path in ('app','about'):
  index=dist/'index.html'
  if not index.exists():raise HTTPException(503,'Build the analytics frontend first.')
  base=f'/cmpdi/workbench/{id}/'
  text=index.read_text().replace('src="./',f'src="{base}').replace('href="./',f'href="{base}')
  # Embedded builds normally emit relative URLs, but keep the secured proxy
  # compatible with an accidental root-base build as well.
  text=re.sub(r'(src|href)="/(?!cmpdi/workbench/)',lambda match:f'{match.group(1)}="{base}',text)
  return HTMLResponse(text,headers={'Content-Security-Policy':"frame-ancestors 'self'",'Cache-Control':'no-store'})
 file=(dist/path).resolve()
 if not file.is_relative_to(dist.resolve()) or not file.is_file():raise HTTPException(404,'Asset not found.')
 return FileResponse(file)

export_lock=asyncio.Lock()
async def save_report(request,p,a):
 async with export_lock:return await _save_report(request,p,a)

async def _save_report(request,p,a):
 body=await bounded_body(request,30*1024*1024)
 try:data=json.loads(body)
 except ValueError:raise HTTPException(422,'Invalid report export.')
 content=data.get('content','');png=data.get('png','');title=str(data.get('title') or a['title'])[:160]
 if not isinstance(content,str) or not content.strip():raise HTTPException(422,'Generate report content before saving.')
 if not isinstance(png,str) or not png.startswith('data:image/png;base64,'):raise HTTPException(422,'A rendered report image is required to preserve charts.')
 try:decoded=base64.b64decode(png.split(',',1)[1],validate=True)
 except ValueError:raise HTTPException(422,'Invalid report image.')
 if not decoded.startswith(b'\x89PNG\r\n\x1a\n'):raise HTTPException(422,'Invalid PNG.')
 rid=str(uuid4());repo=repository();folder=repo.root/a['target_entity']/a['target_family']/'report_generated'/rid
 if not folder.resolve().is_relative_to(repo.root) or any(x.is_symlink() for x in [folder,*folder.parents]):raise HTTPException(403,'Unsafe report destination.')
 images=data.get('chart_images',{})
 if not isinstance(images,dict) or len(images)>100:raise HTTPException(422,'Invalid chart assets.')
 parsed_images={}
 for chart_id,image in images.items():
  if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',chart_id) or not isinstance(image,str) or not image.startswith('data:image/png;base64,'):raise HTTPException(422,'Invalid chart image.')
  try:raw=base64.b64decode(image.split(',',1)[1],validate=True)
  except ValueError:raise HTTPException(422,'Invalid chart encoding.')
  if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise HTTPException(422,'Invalid chart PNG.')
  parsed_images[chart_id]=raw
 if any(chart_id not in parsed_images for chart_id in re.findall(r'chart://([a-zA-Z0-9_-]+)',content)):raise HTTPException(422,'Wait for all report charts to render before saving.')
 state=await upstream(p.id,a['id'],'/api/sessions/load','POST',{'id':a['id']})
 report_key=str(data.get('report_id') or 'legacy')
 if len(report_key)>150:raise HTTPException(422,'Invalid report identifier.')
 revision=repo.next_report_revision(hashlib.sha256((a['id']+':'+report_key).encode()).hexdigest())
 folder.mkdir(parents=True)
 for chart_id,raw in parsed_images.items():
  (folder/'charts').mkdir(exist_ok=True);(folder/'charts'/(chart_id+'.png')).write_bytes(raw)
  content=content.replace('chart://'+chart_id,'charts/'+chart_id+'.png')
 content+='\n\n---\n## Source appendix\n\nAnalytical draft; verify figures before official use.\n\n'+ '\n'.join('- '+x['relative_path']+' — SHA256 `'+x['sha256']+'`' for x in a['sources'])
 (folder/'report.md').write_text(content,encoding='utf8');(folder/'report.png').write_bytes(decoded)
 manifest={'id':rid,'title':title,'status':'analytical-draft','analysis_id':a['id'],'created':time.time(),'target_entity':a['target_entity'],'target_family':a['target_family'],'scope_entities':a['scope_entities'],'missing_entities':a['missing_entities'],'period':a['period'],'sources':a['sources'],'charts':data.get('charts',[]),'notice':'Model-assisted draft. Verify calculations, units and evidence before official use.'}
 manifest.update(revision);manifest['report_key']=report_key;manifest['model']=data.get('model')
 atomic_json(folder/'manifest.json',manifest)
 atomic_json(folder/'analysis-state.json',state)
 with zipfile.ZipFile(folder/'report.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
  for file in folder.rglob('*'):
   if file.is_file() and file.name!='report.zip':archive.write(file,file.relative_to(folder).as_posix())
 # Immutable hard links give each subsidiary a report library without doubling output bytes.
 library=repo.root/a['target_entity']/'report'/rid
 if not library.resolve().is_relative_to(repo.root) or any(x.is_symlink() for x in [library,*library.parents]):raise HTTPException(403,'Unsafe report library.')
 for file in folder.rglob('*'):
  if file.is_file():
   destination=library/file.relative_to(folder);destination.parent.mkdir(parents=True,exist_ok=True)
   try:os.link(file,destination)
   except OSError:shutil.copy2(file,destination)
 atomic_json(repo.root/a['target_entity']/'report'/(rid+'.json'),{'id':rid,'title':title,'relative_path':folder.relative_to(repo.root).as_posix()})
 repo.register_report(p.id,rid,folder,title,revision)
 audit_status=None
 if data.get('send_for_audit') and a['target_entity'] in OPERATING:
  audit_status=repo.submit_audit(rid,p.id,a['target_entity'],a['target_family'])['status']
 return {'id':rid,'relative_path':folder.relative_to(repo.root).as_posix(),'audit_status':audit_status,**revision}

@router.get('/api/cmpdi/reports')
async def reports(p:Principal=Depends(analyst)):
 repo=repository();code=entity_scope(p);items=[];audits={item['report_id']:item for item in repo.audits(code)}
 for r in repo.reports(None):
  relative=repo.report_path(r['id'],None).relative_to(repo.root)
  entity=relative.parts[0];audit_item=audits.get(r['id'],{});audit_status=audit_item.get('status');report_family=audit_item.get('category') or relative.parts[1]
  if p.profile['role']=='subsidiary':visible=entity==code and audit_status=='submitted_to_cmpdi'
  else:visible=audit_status=='submitted_to_cmpdi' or (r['owner']==p.id and (entity=='CMPDI' or audit_status in (None,'rejected')))
  if visible:
   public={key:value for key,value in r.items() if key!='owner'}
   items.append({**public,'entity':entity,'family':report_family,'can_submit':r['owner']==p.id and entity in OPERATING and audit_status in (None,'rejected'),'audit_status':audit_status})
 return items
@router.post('/api/cmpdi/reports/generate',status_code=201)
async def generate_report(data:QuickReportInput,p:Principal=Depends(analyst)):
 repo=repository();catalog=(await asyncio.to_thread(submissions.versioned_catalog,repo,entity_scope(p),True))['files'];items={e['id']:e for e in catalog}
 code=entity_scope(p)
 if code and (data.target_entity!=code or set(data.scope_entities)!={code}):raise HTTPException(403,'Select only your own subsidiary and report destination.')
 # CMPDI can produce a consolidated report for any operating report family;
 # technical families remain available for CMPDI-owned source data.
 families={**TECHNICAL,**PRODUCTION} if data.target_entity=='CMPDI' else PRODUCTION
 if data.target_entity not in ENTITIES or data.target_family not in families:raise HTTPException(422,'Choose a valid report destination.')
 selected=[];seen=set()
 if data.source_version is not None:
  if not data.source_family:raise HTTPException(422,'Choose a report family for the selected version.')
  if data.source_family not in ({**TECHNICAL,**PRODUCTION}):raise HTTPException(422,'Choose a valid source report family.')
  selected=[entry for entry in catalog if entry.get('supported') and entry.get('family')==data.source_family and entry.get('version')==data.source_version and (not data.source_cadence or entry.get('cadence')==data.source_cadence) and (not data.source_period or entry.get('period')==data.source_period) and entry.get('entity') in data.scope_entities]
  if not selected:raise HTTPException(422,'No supported files were found for that report version. Refresh the catalog and choose another version.')
 else:
  for choice in data.inputs:
   entry=items.get(choice.file_id)
   if not entry or not entry['supported']:raise HTTPException(422,'A selected source is missing or unsupported. Refresh the data list.')
   if entry['entity'] not in data.scope_entities:raise HTTPException(422,'A selected source is outside the requested scope.')
   if entry['id'] in seen:raise HTTPException(422,'Select each source once.')
   seen.add(entry['id']);selected.append(entry)
 source={'family':data.source_family,'version':data.source_version,'cadence':data.source_cadence,'period':data.source_period} if data.source_version is not None else None
 result=await asyncio.to_thread(quick_report.generate,repo,p.id,data.title,data.period,data.target_entity,data.target_family,selected,source)
 result['source_family']=data.source_family
 result['source_version']=data.source_version
 result['source_cadence']=data.source_cadence
 result['source_period']=data.source_period
 result['can_submit']=data.target_entity in OPERATING
 if data.send_for_audit:
  result['audit_status']=(await asyncio.to_thread(repo.submit_audit,result['id'],p.id,data.target_entity,data.target_family))['status']
 return result
@router.get('/api/cmpdi/reports/{id}/{artifact}')
async def artifact(id:UUID,artifact:str,p:Principal=Depends(analyst)):
 if artifact not in ('report.md','report.png','report.pdf','manifest.json','report.zip'):raise HTTPException(404,'Artifact not found.')
 repo=repository();folder=repo.report_path(str(id),None);entity=folder.relative_to(repo.root).parts[0];scope=entity_scope(p)
 if scope and entity!=scope:raise HTTPException(404,'Report not found.')
 if p.profile['role']=='cmpdi' and entity in OPERATING:
  report=next((item for item in repo.reports(None) if item['id']==str(id)),None)
  audit=next((item for item in repo.audits(None) if item['report_id']==str(id)),None);status=audit and audit['status']
  if not (status=='submitted_to_cmpdi' or report and report['owner']==p.id and status in (None,'rejected')):raise HTTPException(404,'Report not found.')
 if not (folder/artifact).is_file():raise HTTPException(404,'Artifact not found.')
 return FileResponse(folder/artifact,filename=artifact,headers={'Content-Disposition':f'attachment; filename="{artifact}"'})

@router.post('/api/cmpdi/reports/{id}/audit',status_code=201)
async def submit_report_audit(id:UUID,data:AuditSubmission,p:Principal=Depends(analyst)):
 repo=repository();folder=repo.report_path(str(id),None);entity=folder.relative_to(repo.root).parts[0];scope=entity_scope(p)
 if scope and entity!=scope:raise HTTPException(404,'Report not found.')
 if entity not in OPERATING:raise HTTPException(422,'Choose an operating subsidiary as the report destination before sending it for audit.')
 return await asyncio.to_thread(repo.submit_audit,str(id),p.id,entity,data.category)

@router.get('/api/cmpdi/audits')
async def audit_queue(p:Principal=Depends(analyst)):
 if p.profile['role']=='cmpdi':return []
 items=await asyncio.to_thread(repository().audits,entity_scope(p))
 return [item for item in items if item['status'] not in ('submitted_to_cmpdi','approved')]

@router.post('/api/cmpdi/audits/{id}/decision')
async def audit_decision(id:UUID,data:AuditDecision,p:Principal=Depends(analyst)):
 position=p.profile.get('review_position','contributor')
 if p.profile['role']!='subsidiary' or position not in ('assistant_manager','manager'):raise HTTPException(403,'Only an assistant manager or manager can review audit requests.')
 item=repository().audit(str(id));scope=entity_scope(p)
 if not scope or item['entity']!=scope:raise HTTPException(404,'Audit item not found.')
 return await asyncio.to_thread(repository().decide_audit,str(id),p.id,position,data.decision,data.comment)

from .providers import ProviderInput,add_provider,all_providers,public_config,save as save_providers
provider_lock=asyncio.Lock()
@router.get('/api/cmpdi/providers')
async def providers(p:Principal=Depends(cmpdi)):
 return [public_config(x) for x in all_providers()]
@router.post('/api/cmpdi/providers',status_code=201)
async def create_provider(data:ProviderInput,p:Principal=Depends(cmpdi)):
 async with provider_lock:return await asyncio.to_thread(add_provider,data)
@router.delete('/api/cmpdi/providers/{id}')
async def remove_provider(id:UUID,p:Principal=Depends(cmpdi)):
 async with provider_lock:
  items=all_providers();filtered=[x for x in items if x['id']!=str(id)]
  if len(items)==len(filtered):raise HTTPException(404,'Provider not found.')
  await asyncio.to_thread(save_providers,filtered)
 return {'ok':True}

@router.post('/api/cmpdi/workbench-sessions/revoke')
async def revoke_sessions(p:Principal=Depends(analyst)):
 for key,value in list(sessions.items()):
  if value['owner']==p.id:sessions.pop(key,None)
 return {'ok':True}

# Neutral aliases; legacy CMPDI URLs remain for existing workbench clients.
for route in list(router.routes):
 if route.path.startswith('/api/cmpdi/') and '/providers' not in route.path:
  router.add_api_route(route.path.replace('/api/cmpdi/','/api/analytics/'),route.endpoint,methods=list(route.methods),status_code=route.status_code)

upload_lock=asyncio.Lock()
@router.get('/api/analytics/submissions')
async def submission_history(p:Principal=Depends(analyst)):
 repo=repository();items=await asyncio.to_thread(submissions.history,repo,entity_scope(p));extractions=ocr.list_jobs(repo,entity_scope(p))
 for item in items:
  for file in item['files']:
   job=next((j for j in extractions if j['submission_id']==item['id'] and j['filename']==file['name']),None)
   if job:
    file['extraction_status']=job['status']
    file['status']=job['status']
  item['pending_extraction']=sum(f['status'] in ('pending_extraction','queued','running') for f in item['files'])
  item['extraction_issues']=sum(f['status'] in ('failed','partial') for f in item['files'])
 return items

@router.get('/api/analytics/schedules')
async def reporting_schedules(p:Principal=Depends(analyst)):
 return await asyncio.to_thread(submissions.schedules,repository(),entity_scope(p))

@router.get('/api/analytics/vault')
async def vault_entries(path:str=Query('',max_length=2000),q:str=Query('',max_length=120),kind:str=Query('all',pattern='^(all|folders|tables|documents|images|archives)$'),days:int=Query(0,ge=0,le=366),sort:str=Query('name',pattern='^(name|name_desc|modified|modified_asc)$'),offset:int=Query(0,ge=0),entity:str=Query('',max_length=16),report:str=Query('',max_length=64),p:Principal=Depends(member)):
 return await asyncio.to_thread(vault.browse,repository(),path=path,scope=entity_scope(p),query=q.strip(),kind=kind,days=days,sort=sort,offset=offset,entity_filter=entity,report_filter=report)

@router.get('/api/analytics/vault/structure')
async def vault_structure(p:Principal=Depends(member)):
 repo=repository();scope=entity_scope(p)
 schedule=await asyncio.to_thread(submissions.schedules,repo,scope)
 records=await asyncio.to_thread(submissions.history,repo,scope)
 visible=[]
 for record in records:
  visible.append({key:record.get(key) for key in ('id','entity','family','cadence','period','version','previous_id','uploaded_at','data_prefix','pending_extraction')}|{'files':[{key:file.get(key) for key in ('name','bytes','status')} for file in record.get('files',[])]})
 return {'entities':list(schedule['subsidiaries']),'families':schedule['subsidiaries'],'submissions':visible,'timezone':schedule['timezone']}

@router.get('/api/analytics/vault/archive')
async def vault_archive(id:UUID,p:Principal=Depends(member)):
 repo=repository();record=next((item for item in submissions.history(repo,entity_scope(p)) if item['id']==str(id)),None)
 if not record:raise HTTPException(404,'Version not found.')
 path=repo.root/record['entity']/record['family']/'submissions'/str(id)/'source.zip'
 if not path.is_file():raise HTTPException(404,'Version archive not found.')
 return FileResponse(path,filename=f"{record['entity']}-{record['family']}-{record['period']}-v{record['version']}.zip")

@router.get('/api/analytics/vault/file')
async def vault_file(path:str=Query(...,max_length=2000),p:Principal=Depends(member)):
 repo=repository();target=vault.resolve(repo,path,entity_scope(p))
 if path==vault.SCHEDULE:
  data=await asyncio.to_thread(submissions.schedules,repo,entity_scope(p))
  return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="reporting_schedule.json"','X-Content-Type-Options':'nosniff'})
 if not target.is_file():raise HTTPException(404,'File not found.')
 return FileResponse(target,filename=target.name,media_type='application/octet-stream',headers={'X-Content-Type-Options':'nosniff'})

@router.get('/api/analytics/vault/preview')
async def vault_preview(path:str=Query(...,max_length=2000),p:Principal=Depends(member)):
 repo=repository();target=vault.resolve(repo,path,entity_scope(p))
 if not target.is_file() or target.suffix.lower()!='.csv':raise HTTPException(422,'Preview is available for CSV files.')
 rows=[]
 try:
  with target.open('r',encoding='utf-8-sig',newline='',errors='replace') as source:
   reader=csv.reader(source)
   for index,row in enumerate(reader):
    if index>=101:break
    rows.append([str(cell)[:500] for cell in row[:50]])
 except (OSError,csv.Error):raise HTTPException(422,'This CSV could not be previewed.') from None
 return {'name':target.name,'rows':rows,'truncated':index>=100 if rows else False,'max_columns':50}


@router.post('/api/analytics/submissions',status_code=201)
async def upload_submission(request:Request,family:str,cadence:str,period:str,entity:str='',p:Principal=Depends(analyst)):
 code=entity_scope(p)
 if p.profile['role']=='cmpdi':
  code=entity.strip().upper()
  if code not in OPERATING:raise HTTPException(422,'Choose a valid production subsidiary.')
 if not code:raise HTTPException(403,'ZIP submission is available to production subsidiaries.')
 if request.headers.get('content-type','').split(';')[0] not in ('application/zip','application/octet-stream'):raise HTTPException(415,'Send a ZIP archive.')
 repo=repository();size=0
 fd,name=tempfile.mkstemp(prefix='incoming-',suffix='.zip',dir=repo.processing)
 try:
  with os.fdopen(fd,'wb') as output:
   async for chunk in request.stream():
    size+=len(chunk)
    if size>submissions.MAX_UPLOAD:raise HTTPException(413,'ZIP upload limit is 256 MiB.')
    await asyncio.to_thread(output.write,chunk)
  async with upload_lock:
   task=asyncio.create_task(asyncio.to_thread(submissions.ingest,repo,Path(name),code,p.id,family,cadence,period))
   try:
    result=await asyncio.shield(task)
    return result
   except asyncio.CancelledError:
    await task
    raise
 finally:Path(name).unlink(missing_ok=True)

@router.get('/api/analytics/submissions/{id}/archive')
async def submission_archive(id:UUID,p:Principal=Depends(analyst)):
 record=next((x for x in submissions.history(repository(),entity_scope(p)) if x['id']==str(id)),None)
 if not record:raise HTTPException(404,'Submission not found.')
 path=repository().root/record['entity']/record['family']/'submissions'/str(id)/'source.zip'
 return FileResponse(path,filename=f"{record['entity']}-{record['family']}-{record['period']}-v{record['version']}.zip")

class ExtractionInput(BaseModel):
 submission_id:UUID
 filename:str=Field(min_length=1,max_length=240)

@router.get('/api/analytics/extractions')
async def extraction_list(p:Principal=Depends(analyst)):
 return {'engine_available':bool(ocr.engine()),'jobs':ocr.list_jobs(repository(),entity_scope(p))}

@router.post('/api/analytics/extractions',status_code=202)
async def start_extraction(data:ExtractionInput,p:Principal=Depends(analyst)):
 return ocr.enqueue(repository(),str(data.submission_id),data.filename,p.id,entity_scope(p))

@router.get('/api/analytics/extractions/{id}/preview')
async def extraction_preview(id:UUID,name:str,p:Principal=Depends(analyst)):
 repo=repository();job=ocr.get(repo,str(id),entity_scope(p));return ocr.preview(repo,job,name)

@router.get('/api/analytics/extractions/{id}/artifact')
async def extraction_artifact(id:UUID,name:str,p:Principal=Depends(analyst)):
 repo=repository();job=ocr.get(repo,str(id),entity_scope(p));return FileResponse(ocr.artifact_path(repo,job,name))

class ExtractionReview(BaseModel):
 name:str=Field(min_length=1,max_length=120)
 corrected_csv:str|None=Field(default=None,max_length=5*1024**2)

@router.post('/api/analytics/extractions/{id}/approve')
async def extraction_approve(id:UUID,data:ExtractionReview,p:Principal=Depends(analyst)):
 async with ocr.review_lock:
  repo=repository();job=ocr.get(repo,str(id),entity_scope(p))
  try:return ocr.approve(repo,job,data.name,p.id,data.corrected_csv)
  except csv.Error:raise HTTPException(422,'Invalid corrected CSV.') from None
