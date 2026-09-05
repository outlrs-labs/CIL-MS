"""Local report repository: organizational originals are never modified."""
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException

PRODUCTION = {
 'production_offtake': {'name':'Production and off-take report','cadences':['daily','monthly']},
 'environmental_compliance': {'name':'Environmental clearance and compliance report','cadences':['half-yearly']},
 'financial': {'name':'Financial report','cadences':['quarterly','annual']},
 'operational_statistics': {'name':'Operational statistic report','cadences':['monthly']},
 'washery_operations': {'name':'Washery operational report','cadences':['daily','monthly']},
}
TECHNICAL = {
 'annual': {'name':'Annual report','cadences':['annual'],'audience':'public'},
 'land_reclamation': {'name':'Land restoration / reclamation monitoring report','cadences':['annual'],'audience':'public'},
 'geological_exploration': {'name':'Geological and exploration reports','cadences':['project-based'],'audience':'internal'},
 'hydrology_groundwater': {'name':'Hydrological studies and groundwater modeling','cadences':['project-based','annual'],'audience':'internal'},
 'project_feasibility': {'name':'Project / feasibility report','cadences':['event-driven'],'audience':'internal'},
 'specialized_surveys': {'name':'Specialized environmental and topographical surveys','cadences':['unspecified'],'audience':'internal'},
}
OPERATING=('ECL','BCCL','CCL','NCL','WCL','SECL','MCL')
ENTITIES=(*OPERATING,'CMPDI')
FORMATS={'.csv','.xlsx','.json','.parquet'}

def atomic_json(path, value):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
 tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,path)

class Repository:
 def __init__(self,root:Path,processing:Path):
  self.root=root.resolve();self.processing=processing.resolve()
  self.processing.mkdir(parents=True,exist_ok=True)
  with self.db() as db:
   db.execute('create table if not exists analyses(id text primary key, owner text not null, payload text not null)')
   db.execute('create table if not exists reports(id text primary key, owner text not null, path text not null, title text not null, created real not null)')
   db.execute('create table if not exists audit_reviews(report_id text primary key,submitter text not null,entity text not null,category text not null default "",status text not null,assistant_reviewer text,manager_reviewer text,comment text not null default "",updated real not null)')
   columns={row[1] for row in db.execute('pragma table_info(audit_reviews)')}
   if 'category' not in columns:db.execute('alter table audit_reviews add column category text not null default ""')
   legacy=db.execute('select a.report_id,r.path from audit_reviews a join reports r on r.id=a.report_id where a.category=""').fetchall()
   for report_id,path in legacy:
    resolved=Path(path).resolve()
    if resolved.is_relative_to(self.root) and len(resolved.relative_to(self.root).parts)>1:
     db.execute('update audit_reviews set category=? where report_id=?',(resolved.relative_to(self.root).parts[1],report_id))
 def db(self):
  db=sqlite3.connect(self.processing/'catalog.sqlite3',timeout=30);db.execute('pragma journal_mode=WAL');return db
 def initialize(self):
  for entity in ENTITIES:
   for family in (TECHNICAL if entity=='CMPDI' else PRODUCTION):
    for kind in ('data','report_generated'):(self.root/entity/family/kind).mkdir(parents=True,exist_ok=True)
   (self.root/entity/'report').mkdir(parents=True,exist_ok=True)
 def catalog(self):
  files=[];folders=[]
  for entity in ENTITIES:
   for family,info in (TECHNICAL if entity=='CMPDI' else PRODUCTION).items():
    folder=self.root/entity/family/'data';folders.append({'entity':entity,'family':family,**info})
    if not folder.is_dir() or folder.is_symlink():continue
    for base,dirs,names in os.walk(folder,followlinks=False):
     dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink()]
     for name in sorted(names):
      path=Path(base)/name
      if path.is_symlink() or not path.is_file() or path.name.startswith('.'):continue
      resolved=path.resolve()
      if not resolved.is_relative_to(self.root):continue
      stat=path.stat();relative=path.relative_to(self.root).as_posix()
      fingerprint=f'{relative}:{stat.st_size}:{stat.st_mtime_ns}'
      files.append({'id':hashlib.sha256(fingerprint.encode()).hexdigest(),'entity':entity,'family':family,'name':name,'relative_path':relative,'bytes':stat.st_size,'modified':stat.st_mtime,'supported':path.suffix.lower() in FORMATS})
  return {'files':files,'folders':folders,'root_label':'Data/cil','entities':list(ENTITIES)}
 def put_analysis(self,value):
  with self.db() as db:db.execute('insert or replace into analyses values(?,?,?)',(value['id'],value['owner'],json.dumps(value)))
 def get_analysis(self,id,owner):
  with self.db() as db:row=db.execute('select payload from analyses where id=? and owner=?',(id,owner)).fetchone()
  if not row:raise HTTPException(404,'Analysis not found.')
  return json.loads(row[0])
 def list_analyses(self,owner):
  with self.db() as db:rows=db.execute('select payload from analyses where owner=? order by rowid desc',(owner,)).fetchall()
  return [json.loads(r[0]) for r in rows]
 def snapshot(self,entry,analysis_id):
  path=self.root/entry['relative_path'];resolved=path.resolve()
  if not resolved.is_relative_to(self.root) or any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('Unsafe source path.')
  before=path.stat()
  if hashlib.sha256(f"{entry['relative_path']}:{before.st_size}:{before.st_mtime_ns}".encode()).hexdigest()!=entry['id']:raise ValueError('Source changed. Refresh the catalog.')
  output=self.processing/'snapshots'/analysis_id/(entry['id']+path.suffix.lower());output.parent.mkdir(parents=True,exist_ok=True)
  digest=hashlib.sha256()
  with path.open('rb') as src,output.open('xb') as dst:
   for block in iter(lambda:src.read(1024*1024),b''):digest.update(block);dst.write(block)
  after=path.stat()
  if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
   output.unlink();raise ValueError('Source changed during snapshot; create a new analysis.')
  return {**entry,'sha256':digest.hexdigest(),'snapshot':str(output.relative_to(self.processing))}
 def next_report_revision(self,series):
  from .submissions import initialize
  initialize(self)
  with self.db() as db:row=db.execute('select id,version from report_revisions where series=? order by version desc limit 1',(series,)).fetchone()
  return {'series':series,'version':row[1]+1 if row else 1,'previous_id':row[0] if row else None}
 def register_report(self,owner,id,path,title,revision=None):
  with self.db() as db:
   db.execute('insert into reports values(?,?,?,?,?)',(id,owner,str(path),title,time.time()))
   if revision:db.execute('insert into report_revisions values(?,?,?,?)',(id,revision['series'],revision['version'],revision['previous_id']))
 def reports(self,owner):
  with self.db() as db:rows=db.execute('select id,title,created,owner from reports'+(' where owner=?' if owner else '')+' order by created desc',(owner,) if owner else ()).fetchall()
  items=[dict(zip(('id','title','created','owner'),r)) for r in rows]
  from .submissions import initialize
  initialize(self)
  with self.db() as db:
   for item in items:
    revision=db.execute('select series,version,previous_id from report_revisions where id=?',(item['id'],)).fetchone()
    item.update(dict(zip(('series','version','previous_id'),revision)) if revision else {'series':item['id'],'version':1,'previous_id':None})
  return items
 def report_labels(self):
  """Return presentation metadata without exposing repository paths to clients."""
  from .submissions import initialize
  initialize(self)
  with self.db() as db:
   rows=db.execute('select r.id,r.path,r.title,coalesce(a.entity,""),coalesce(a.category,""),coalesce(v.version,1) from reports r left join audit_reviews a on a.report_id=r.id left join report_revisions v on v.id=r.id').fetchall()
  labels={}
  for report_id,path,title,entity,category,version in rows:
   resolved=Path(path).resolve()
   if not resolved.is_relative_to(self.root):continue
   relative=resolved.relative_to(self.root)
   parts=relative.parts
   labels[report_id]={'id':report_id,'path':relative.as_posix(),'title':title,'entity':entity or (parts[0] if parts else ''),'category':category or (parts[1] if len(parts)>1 else ''),'version':version or 1}
  return labels
 def report_path(self,id,owner):
  with self.db() as db:row=db.execute('select path from reports where id=?'+(' and owner=?' if owner else ''),(id,owner) if owner else (id,)).fetchone()
  if not row:raise HTTPException(404,'Report not found.')
  path=Path(row[0]).resolve()
  if not path.is_relative_to(self.root):raise HTTPException(403,'Invalid report location.')
  return path
 def submit_audit(self,report_id,submitter,entity,category):
  if entity not in OPERATING:raise HTTPException(422,'Choose an operating subsidiary as the report destination before sending it for audit.')
  if category not in PRODUCTION:raise HTTPException(422,'Choose a valid subsidiary report category.')
  now=time.time()
  with self.db() as db:
   db.execute('begin immediate')
   owner=db.execute('select owner from reports where id=?',(report_id,)).fetchone()
   if not owner:raise HTTPException(404,'Report not found.')
   if owner[0]!=submitter:raise HTTPException(403,'Only the report author can submit it for audit.')
   current=db.execute('select status from audit_reviews where report_id=?',(report_id,)).fetchone()
   if current and current[0] not in ('rejected','changes_requested'):raise HTTPException(409,'This report is already in audit.')
   db.execute('insert into audit_reviews(report_id,submitter,entity,category,status,updated) values(?,?,?,?,?,?) on conflict(report_id) do update set category=excluded.category,status="pending_review",assistant_reviewer=null,manager_reviewer=null,comment="",updated=excluded.updated',(report_id,submitter,entity,category,'pending_review',now))
  return self.audit(report_id)
 def audit(self,report_id):
  from .submissions import initialize
  initialize(self)
  with self.db() as db:row=db.execute('select a.report_id,r.title,r.created,a.submitter,a.entity,a.category,a.status,a.assistant_reviewer,a.manager_reviewer,a.comment,a.updated,v.version,v.previous_id from audit_reviews a join reports r on r.id=a.report_id left join report_revisions v on v.id=r.id where a.report_id=?',(report_id,)).fetchone()
  if not row:raise HTTPException(404,'Audit item not found.')
  item=dict(zip(('report_id','title','created','submitter','entity','category','status','assistant_reviewer','manager_reviewer','comment','updated','version','previous_id'),row));item['version']=item['version'] or 1;return item
 def audits(self,scope=None):
  from .submissions import initialize
  initialize(self)
  with self.db() as db:rows=db.execute('select a.report_id,r.title,r.created,a.submitter,a.entity,a.category,a.status,a.assistant_reviewer,a.manager_reviewer,a.comment,a.updated,v.version,v.previous_id from audit_reviews a join reports r on r.id=a.report_id left join report_revisions v on v.id=r.id'+(' where a.entity=?' if scope else '')+' order by a.category,a.updated desc',(scope,) if scope else ()).fetchall()
  keys=('report_id','title','created','submitter','entity','category','status','assistant_reviewer','manager_reviewer','comment','updated','version','previous_id')
  items=[dict(zip(keys,row)) for row in rows]
  for item in items:item['version']=item['version'] or 1
  return items
 def decide_audit(self,report_id,reviewer,position,decision,comment):
  if position!='manager':raise HTTPException(403,'Only the subsidiary manager can review audit requests.')
  item=self.audit(report_id)
  if item['submitter']==reviewer:raise HTTPException(403,'The report author cannot audit their own report.')
  if item['status'] not in ('pending_review','awaiting','assistant_manager_pending','manager_pending'):raise HTTPException(409,'This request is already complete.')
  status={'approve':'submitted_to_cmpdi','await':'awaiting','reject':'rejected'}.get(decision)
  if not status:raise HTTPException(422,'Choose Approve, Await or Reject.')
  column='manager_reviewer'
  if decision not in ('approve','await','reject'):raise HTTPException(422,'Choose Approve, Await or Reject.')
  if decision=='reject' and not comment.strip():raise HTTPException(422,'Explain what needs to change.')
  with self.db() as db:
   result=db.execute(f'update audit_reviews set status=?,{column}=?,comment=?,updated=? where report_id=? and status=?',(status,reviewer,comment.strip(),time.time(),report_id,item['status']))
   if result.rowcount!=1:raise HTTPException(409,'This report has already been reviewed. Refresh the queue.')
  return self.audit(report_id)
