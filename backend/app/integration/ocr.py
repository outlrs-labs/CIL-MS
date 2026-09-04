"""Persistent, entity-scoped OCR jobs; reviewed outputs join the source catalog."""
import asyncio
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from . import submissions
from .repository import atomic_json

tasks=set()
worker_lock=asyncio.Lock()
review_lock=asyncio.Lock()

def initialize(repo):
    with repo.db() as db:db.execute('create table if not exists extractions(id text primary key, entity text, payload text)')

def save(repo,job):
    with repo.db() as db:db.execute('insert or replace into extractions values(?,?,?)',(job['id'],job['entity'],json.dumps(job)))

def list_jobs(repo,entity=None):
    initialize(repo)
    with repo.db() as db:rows=db.execute('select payload from extractions'+(' where entity=?' if entity else '')+' order by rowid desc',(entity,) if entity else ()).fetchall()
    return [json.loads(r[0]) for r in rows]

def get(repo,id,entity=None):
    job=next((j for j in list_jobs(repo,entity) if j['id']==id),None)
    if not job:raise HTTPException(404,'Extraction not found.')
    return job

def engine():
    return shutil.which('tesseract') or next((str(p) for p in (Path('/opt/homebrew/bin/tesseract'),Path('/usr/local/bin/tesseract')) if p.is_file()),None)

def source_record(repo,submission_id,filename,entity):
    record=next((s for s in submissions.history(repo,entity) if s['id']==submission_id),None)
    if not record:raise HTTPException(404,'Submission not found.')
    entry=next((f for f in record['files'] if f['name']==filename and Path(filename).suffix.lower() in {'.pdf','.png','.jpg','.jpeg','.tif','.tiff'}),None)
    if not entry:raise HTTPException(422,'Choose a PDF or image from this submission.')
    source=repo.root/record['data_prefix']/filename
    if not source.resolve().is_relative_to(repo.root) or any(p.is_symlink() for p in (source,*source.parents)):raise HTTPException(403,'Unsafe source path.')
    return record,entry,source

def enqueue(repo,submission_id,filename,owner,entity):
    record,entry,source=source_record(repo,submission_id,filename,entity)
    # One active job per input; failed jobs may be retried as a new immutable run.
    active=next((j for j in list_jobs(repo,record['entity']) if j['submission_id']==submission_id and j['filename']==filename and j['status'] in ('queued','running')),None)
    if active:return active
    id=str(uuid4());folder=repo.root/record['entity']/record['family']/'extractions'/id
    folder.mkdir(parents=True)
    job={'id':id,'entity':record['entity'],'family':record['family'],'submission_id':submission_id,'filename':filename,'source_sha256':entry['sha256'],'source_path':source.relative_to(repo.root).as_posix(),'folder':folder.relative_to(repo.root).as_posix(),'owner':owner,'created':time.time(),'status':'queued','pages':[],'artifacts':[],'error':None}
    save(repo,job)
    task=asyncio.create_task(run(repo,id));tasks.add(task);task.add_done_callback(tasks.discard)
    return job

async def run(repo,id):
    async with worker_lock:
        job=get(repo,id);job['status']='running';save(repo,job)
        proc=None
        try:
            worker=Path(__file__).with_name('ocr_worker.py')
            proc=await asyncio.create_subprocess_exec(sys.executable,str(worker),str(repo.root),str(repo.processing),id,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(proc.wait(),timeout=900)
            job=get(repo,id)
            if proc.returncode or job['status']=='running':raise RuntimeError('Extraction process failed. Retry the file or inspect the local worker environment.')
        except BaseException as exc:
            if proc and proc.returncode is None:proc.kill();await proc.wait()
            job=get(repo,id);job.update(status='failed',error='Extraction timed out after 15 minutes.' if isinstance(exc,asyncio.TimeoutError) else 'Extraction interrupted or failed. Retry this file.');save(repo,job)
            if isinstance(exc,asyncio.CancelledError):raise

def artifact_path(repo,job,name):
    allowed={a['name'] for a in job['artifacts']}|{p['preview'] for p in job['pages'] if p.get('preview')}
    if name not in allowed:raise HTTPException(404,'Extraction artifact not found.')
    path=(repo.root/job['folder']/name).resolve()
    if not path.is_relative_to((repo.root/job['folder']).resolve()) or not path.is_file():raise HTTPException(404,'Artifact unavailable.')
    return path

def preview(repo,job,name):
    path=artifact_path(repo,job,name)
    if path.suffix!='.csv':raise HTTPException(422,'Choose a CSV artifact.')
    with path.open(newline='',encoding='utf8') as f:
        reader=csv.reader(f);rows=[]
        for row in reader:
            rows.append(row)
            if len(rows)>201:break
    return {'rows':rows[:201],'truncated':len(rows)>201,'name':name}

def approve(repo,job,name,reviewer,corrected_csv=None):
    if job['status'] not in ('needs_review','reviewed','partial'):raise HTTPException(409,'Wait for extraction to complete.')
    artifact=next((a for a in job['artifacts'] if a['name']==name),None)
    if not artifact:raise HTTPException(404,'Artifact not found.')
    if artifact.get('approved'):raise HTTPException(409,'This artifact is already approved. Rerun extraction for a new review revision.')
    source=artifact_path(repo,job,name);target=source.with_name('reviewed-'+source.name)
    if corrected_csv is not None:
        if len(corrected_csv.encode())>5*1024**2:raise HTTPException(413,'Review edit limit is 5 MiB.')
        rows=list(csv.reader(io.StringIO(corrected_csv),strict=True))
        if len(rows)<2 or not all(rows[0]) or len(set(rows[0]))!=len(rows[0]) or any(len(r)!=len(rows[0]) for r in rows):raise HTTPException(422,'Corrected CSV requires unique headers and consistent row widths.')
        with target.open('x',newline='',encoding='utf8') as f:csv.writer(f).writerows(rows)
    else:shutil.copyfile(source,target)
    artifact.update(approved=True,reviewer=reviewer,reviewed_at=time.time(),reviewed_path=target.relative_to(repo.root).as_posix(),sha256=submissions.hash_file(target))
    if all(a.get('approved') for a in job['artifacts'] if a['kind']!='word_positions') and not any(p['status'] in ('failed','no_text') for p in job['pages']):job['status']='reviewed'
    save(repo,job);atomic_json(repo.root/job['folder']/'review.json',job)
    return job

def catalog_files(repo,entity,include_history):
    records=submissions.history(repo,entity);latest={}
    for r in records:latest.setdefault((r['entity'],r['family'],r['cadence'],r['period']),r['id'])
    records={r['id']:r for r in records};files=[];seen=set()
    for job in list_jobs(repo,entity):
        record=records.get(job['submission_id'])
        if not record:continue
        current=latest[(record['entity'],record['family'],record['cadence'],record['period'])]==record['id']
        if not current and not include_history:continue
        for a in job['artifacts']:
            if not a.get('approved'):continue
            identity=(job['submission_id'],job['filename'],a['name'])
            if identity in seen and not include_history:continue
            seen.add(identity)
            path=repo.root/a['reviewed_path'];stat=path.stat();relative=a['reviewed_path']
            files.append({'id':hashlib.sha256(f'{relative}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest(),'entity':record['entity'],'family':record['family'],'name':job['filename']+' · '+a['name'],'relative_path':relative,'bytes':stat.st_size,'modified':stat.st_mtime,'supported':True,'submission_id':record['id'],'version':record['version'],'cadence':record['cadence'],'period':record['period'],'is_latest':current,'extraction_id':job['id'],'source_sha256':job['source_sha256'],'reviewed':True})
    return files
