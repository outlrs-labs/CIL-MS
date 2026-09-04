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
  with self.db() as db:rows=db.execute('select id,title,created from reports'+(' where owner=?' if owner else '')+' order by created desc',(owner,) if owner else ()).fetchall()
  items=[dict(zip(('id','title','created'),r)) for r in rows]
  from .submissions import initialize
  initialize(self)
  with self.db() as db:
   for item in items:
    revision=db.execute('select series,version,previous_id from report_revisions where id=?',(item['id'],)).fetchone()
    item.update(dict(zip(('series','version','previous_id'),revision)) if revision else {'series':item['id'],'version':1,'previous_id':None})
  return items
 def report_path(self,id,owner):
  with self.db() as db:row=db.execute('select path from reports where id=?'+(' and owner=?' if owner else ''),(id,owner) if owner else (id,)).fetchone()
  if not row:raise HTTPException(404,'Report not found.')
  path=Path(row[0]).resolve()
  if not path.is_relative_to(self.root):raise HTTPException(403,'Invalid report location.')
  return path
