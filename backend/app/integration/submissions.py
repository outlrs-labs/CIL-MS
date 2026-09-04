"""Local ZIP ingestion, immutable revisions, and calendar-based reporting obligations."""
import calendar
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from .repository import PRODUCTION, OPERATING, FORMATS, atomic_json

TZ=ZoneInfo('Asia/Kolkata')
ACCEPTED=FORMATS|{'.pdf','.png','.jpg','.jpeg','.tif','.tiff'}
SUPPORTING={'.md','.txt'}
MAX_UPLOAD=256*1024**2
MAX_EXPANDED=1024**3
MAX_FILES=500

def initialize(repo):
 with repo.db() as db:
  db.execute('create table if not exists submissions(id text primary key, entity text, family text, cadence text, period text, version integer, owner text, created real, payload text, unique(entity,family,cadence,period,version))')
  db.execute('create table if not exists report_revisions(id text primary key, series text, version integer, previous_id text, unique(series,version))')

def period_bounds(cadence,period):
 try:
  if cadence=='daily':start=date.fromisoformat(period);end=start+timedelta(days=1)
  elif cadence=='monthly':
   start=datetime.strptime(period,'%Y-%m').date();end=date(start.year+(start.month==12),start.month%12+1,1)
  elif cadence=='quarterly':
   year,q=period.split('-Q');q=int(q);assert 1<=q<=4
   start=date(int(year),(q-1)*3+1,1);end=date(start.year+(q==4),1 if q==4 else start.month+3,1)
  elif cadence=='half-yearly':
   year,h=period.split('-H');h=int(h);assert h in (1,2)
   start=date(int(year),1 if h==1 else 7,1);end=date(start.year+(h==2),7 if h==1 else 1,1)
  elif cadence=='annual':start=date(int(period),1,1);end=date(start.year+1,1,1)
  else:raise ValueError()
  expected=period_key(cadence,start)
  if expected!=period:raise ValueError()
  return start,end
 except (ValueError,AssertionError,OverflowError):raise HTTPException(422,'Invalid reporting period. Use YYYY-MM-DD, YYYY-MM, YYYY-Q1, YYYY-H1 or YYYY for the selected cycle.') from None

def period_key(cadence,d):
 return {'daily':d.isoformat(),'monthly':d.strftime('%Y-%m'),'quarterly':f'{d.year}-Q{(d.month-1)//3+1}','half-yearly':f'{d.year}-H{1 if d.month<=6 else 2}','annual':str(d.year)}[cadence]

def history(repo,entity=None):
 initialize(repo)
 with repo.db() as db:
  rows=db.execute('select payload from submissions'+(' where entity=?' if entity else '')+' order by created desc', (entity,) if entity else ()).fetchall()
 return [json.loads(r[0]) for r in rows]

def schedules(repo,entity=None,now=None):
 now=now or datetime.now(TZ);items=history(repo,entity);result={}
 for code in ([entity] if entity else OPERATING):
  result[code]={}
  for family,info in PRODUCTION.items():
   records=[x for x in items if x['entity']==code and x['family']==family]
   cycles={}
   for cadence in info['cadences']:
    period=period_key(cadence,now.date());start,end=period_bounds(cadence,period)
    previous=period_key(cadence,start-timedelta(days=1))
    same=[x for x in records if x['cadence']==cadence]
    current=next((x for x in same if x['period']==period),None)
    prev=next((x for x in same if x['period']==previous),None)
    cycles[cadence]={'timeline':{'daily':{'hours':24},'monthly':{'calendar_months':1},'quarterly':{'calendar_months':3},'half-yearly':{'calendar_months':6},'annual':{'calendar_months':12}}[cadence], 'last_update':same[0]['uploaded_at'] if same else None,'current_period':period,'due_at':datetime.combine(end,datetime.min.time(),TZ).isoformat(),'status':'submitted' if current else 'awaiting_submission','latest_version':current['version'] if current else None,'previous_period':previous,'previous_period_status':'submitted' if prev else 'missing','pending_extraction':bool(current and current['pending_extraction'])}
   result[code][family]={'name':info['name'],'last_update':records[0]['uploaded_at'] if records else None,'cycles':cycles}
 return {'schema_version':1,'timezone':'Asia/Kolkata','policy':'Calendar periods; due at the start of the next period. Provisional schedule, not statutory deadlines. Previous-period missing flags are informational; no historical backfill obligation is inferred.','subsidiaries':result}

def publish_schedule(repo):
 atomic_json(repo.root/'reporting_schedule.json',schedules(repo))

def ingest(repo,archive,entity,owner,family,cadence,period):
 if entity not in OPERATING:raise HTTPException(403,'Only a production subsidiary can submit data.')
 if family not in PRODUCTION or cadence not in PRODUCTION[family]['cadences']:raise HTTPException(422,'Invalid report family or reporting cycle.')
 start,_=period_bounds(cadence,period)
 if start>datetime.now(TZ).date():raise HTTPException(422,'A future reporting period cannot be submitted yet.')
 initialize(repo)
 base=repo.root/entity/family
 if any(p.is_symlink() for p in [base,*base.parents]):raise HTTPException(403,'Unsafe storage destination.')
 staging=Path(tempfile.mkdtemp(prefix='.submission-',dir=base))
 files=staging/'files';files.mkdir();entries=[];total=0;seen=set()
 try:
  try:
   with zipfile.ZipFile(archive) as z:
    if len(z.infolist())>MAX_FILES*2:raise HTTPException(422,'ZIP contains too many entries.')
    for info in z.infolist():
     name=info.filename
     # Standard zip tools often store paths as ./folder/file.csv.
     while name.startswith('./'):name=name[2:]
     if not name and info.is_dir():continue
     path=PurePosixPath(name)
     if path.as_posix()!=name.rstrip('/') or '\\' in name or '\x00' in name or path.is_absolute() or any(part in ('..','.') or ':' in part for part in path.parts) or not path.parts or len(name)>240:raise HTTPException(422,'ZIP contains an unsafe file path.')
     mode=info.external_attr>>16
     if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):raise HTTPException(422,'ZIP links and special files are not allowed.')
     if info.flag_bits&1:raise HTTPException(422,'Password-protected ZIP files are not supported.')
     if info.is_dir():continue
     if any(p.startswith('.') or p=='__MACOSX' for p in path.parts):continue
     suffix=path.suffix.lower()
     if suffix not in ACCEPTED|SUPPORTING:
      reason='Nested ZIPs are not supported; extract the inner archive first.' if suffix=='.zip' else 'Use CSV, XLSX, JSON, Parquet, PDF or images. Markdown and text documentation may accompany data.'
      raise HTTPException(422,f'Unsupported file "{name}". {reason}')
     if name.casefold() in seen or any(name.casefold().startswith(old+'/') or old.startswith(name.casefold()+'/') for old in seen):raise HTTPException(422,'ZIP contains duplicate or conflicting file paths.')
     seen.add(name.casefold());total+=info.file_size
     if len(seen)>MAX_FILES or total>MAX_EXPANDED or info.file_size>MAX_UPLOAD or info.file_size/max(info.compress_size,1)>200:raise HTTPException(413,'ZIP exceeds file count, expanded-size or compression-ratio limits.')
     target=files.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256();size=0
     with z.open(info) as src,target.open('xb') as dst:
      while chunk:=src.read(1024**2):
       size+=len(chunk)
       if size>info.file_size or size>MAX_UPLOAD:raise HTTPException(413,'Expanded file exceeds its declared size.')
       digest.update(chunk);dst.write(chunk)
     if not size and suffix not in SUPPORTING:raise HTTPException(422,f'ZIP contains an empty data file: "{name}".')
     entries.append({'name':name,'bytes':size,'sha256':digest.hexdigest(),'status':'supporting_document' if suffix in SUPPORTING else 'ready_for_analysis' if suffix in FORMATS else 'pending_extraction'})
  except (zipfile.BadZipFile,RuntimeError,NotImplementedError,EOFError,ValueError) as exc:raise HTTPException(422,'Invalid, damaged or unsupported ZIP archive.') from None
  if not any(x['status']!='supporting_document' for x in entries):raise HTTPException(422,'ZIP contains no supported data files. Include a table, PDF or image alongside any documentation.')
  id=str(uuid4());created=time.time();prefix=f'{entity}/{family}/data/versions/{cadence}/{period}/{id}'
  destination=repo.root/prefix;bundle=base/'submissions'/id
  with repo.db() as db:
   db.execute('begin immediate')
   version=db.execute('select coalesce(max(version),0)+1 from submissions where entity=? and family=? and cadence=? and period=?',(entity,family,cadence,period)).fetchone()[0]
   previous=db.execute('select id from submissions where entity=? and family=? and cadence=? and period=? order by version desc limit 1',(entity,family,cadence,period)).fetchone()
   record={'id':id,'entity':entity,'family':family,'cadence':cadence,'period':period,'version':version,'previous_id':previous[0] if previous else None,'owner':owner,'created':created,'uploaded_at':datetime.fromtimestamp(created,TZ).isoformat(),'data_prefix':prefix,'files':entries,'pending_extraction':sum(x['status']=='pending_extraction' for x in entries),'archive_sha256':hash_file(archive)}
   destination.parent.mkdir(parents=True,exist_ok=True);bundle.mkdir(parents=True)
   try:
    shutil.copyfile(archive,bundle/'source.zip');atomic_json(bundle/'manifest.json',record)
    os.replace(files,destination)
    db.execute('insert into submissions values(?,?,?,?,?,?,?,?,?)',(id,entity,family,cadence,period,version,owner,created,json.dumps(record)))
   except BaseException:
    shutil.rmtree(destination,ignore_errors=True);shutil.rmtree(bundle,ignore_errors=True);raise
  # SQLite is authoritative; the JSON is a rebuildable projection of committed submissions.
  publish_schedule(repo)
  return record
 finally:shutil.rmtree(staging,ignore_errors=True)

def hash_file(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  while chunk:=f.read(1024**2):h.update(chunk)
 return h.hexdigest()

def versioned_catalog(repo,entity=None,include_history=False):
 catalog=repo.catalog();items=history(repo,entity);latest={}
 for record in items:latest.setdefault((record['entity'],record['family'],record['cadence'],record['period']),record['id'])
 records={r['data_prefix']:r for r in items};files=[]
 for f in catalog['files']:
  if entity and f['entity']!=entity:continue
  if '/data/versions/' in f['relative_path']:
   record=next((r for prefix,r in records.items() if f['relative_path'].startswith(prefix+'/')),None)
   if not record:continue # Uncommitted/orphaned data is never discoverable.
   current=latest[(record['entity'],record['family'],record['cadence'],record['period'])]==record['id']
   if not include_history and not current:continue
   f={**f,'submission_id':record['id'],'version':record['version'],'cadence':record['cadence'],'period':record['period'],'is_latest':current}
  files.append(f)
 from . import ocr
 catalog['files']=files+ocr.catalog_files(repo,entity,include_history)
 if entity:
  catalog['entities']=[entity];catalog['folders']=[f for f in catalog['folders'] if f['entity']==entity]
 return catalog
