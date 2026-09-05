import io,json,stat,zipfile
from datetime import datetime
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.auth import Principal,principal
from app.main import app
from app.integration import api,submissions
from app.integration.repository import Repository

@pytest.fixture
def repo(tmp_path,monkeypatch):
 r=Repository(tmp_path/'cil',tmp_path/'processing');r.initialize();submissions.initialize(r)
 monkeypatch.setattr(api,'repository',lambda:r)
 yield r
 app.dependency_overrides.clear()

def actor(code='BCCL',role='subsidiary'):
 return Principal('user-'+code,'fixture',{'role':role,'must_change_password':False,'active':True},{'code':code,'active':True,'kind':'technical' if role=='cmpdi' else 'operating'})
def zip_bytes(entries):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  for name,data in entries:z.writestr(name,data)
 return b.getvalue()
def upload(c,entries,**params):
 return c.post('/api/analytics/submissions',params={'family':'production_offtake','cadence':'daily','period':'2026-08-01',**params},content=zip_bytes(entries),headers={'Content-Type':'application/zip'})

def test_zip_versioning_calendar_and_scope(repo):
 app.dependency_overrides[principal]=lambda:actor()
 with TestClient(app) as c:
  first=upload(c,[('a.csv','value\n1\n'),('nested/b.json','[{"value":2}]')]);assert first.status_code==201,first.text
  second=upload(c,[('a.csv','value\n3\n')]);assert second.status_code==201
  a,b=first.json(),second.json();assert (a['version'],b['version'],b['previous_id'])==(1,2,a['id'])
  assert (repo.root/a['data_prefix']/'a.csv').read_text()=='value\n1\n'
  current=c.get('/api/analytics/catalog').json();assert current['entities']==['BCCL'];assert len(current['files'])==1;assert current['files'][0]['version']==2
  assert len(c.get('/api/analytics/catalog?include_history=true').json()['files'])==3
  assert c.get('/api/analytics/submissions/'+a['id']+'/archive').status_code==200
  monthly=upload(c,[('m.csv','value\n5')],cadence='monthly',period='2026-08');assert monthly.json()['version']==1
  schedule=json.loads((repo.root/'reporting_schedule.json').read_text());assert len(schedule['subsidiaries'])==7
  cycles=schedule['subsidiaries']['BCCL']['production_offtake']['cycles'];assert cycles['daily']['last_update'] and cycles['monthly']['last_update']
  app.dependency_overrides[principal]=lambda:actor('SECL')
  assert c.get('/api/analytics/catalog').json()['files']==[]
  assert c.get('/api/analytics/submissions').json()==[]
  assert c.get('/api/analytics/submissions/'+a['id']+'/archive').status_code==404
  assert c.post('/api/analytics/analyses',json={'title':'Cross entity','scope_entities':['BCCL'],'target_entity':'BCCL','target_family':'production_offtake','inputs':[{'file_id':current['files'][0]['id']}]}).status_code==403
  app.dependency_overrides[principal]=lambda:actor('CMPDI','cmpdi')
  assert len(c.get('/api/analytics/submissions').json())==3
  assert upload(c,[('a.csv','value\n1')]).status_code==422
  delegated=upload(c,[('cmpdi.csv','value\n1')],entity='BCCL',period='2026-08-02')
  assert delegated.status_code==201 and delegated.json()['entity']=='BCCL'
  assert upload(c,[('a.csv','value\n1')],entity='CMPDI').status_code==422

def test_reject_mixed_revisions(repo):
 app.dependency_overrides[principal]=lambda:actor()
 with TestClient(app) as c:
  upload(c,[('a.csv','value\n1')]);upload(c,[('a.csv','value\n2')])
  files=c.get('/api/analytics/catalog?include_history=true').json()['files']
  r=c.post('/api/analytics/analyses',json={'title':'Mixed revisions','scope_entities':['BCCL'],'target_entity':'BCCL','target_family':'production_offtake','inputs':[{'file_id':f['id']} for f in files]})
  assert r.status_code==422 and 'mix revisions' in r.json()['detail']

@pytest.mark.parametrize('name',['../escape.csv','/escape.csv','a/../../escape.csv','a\\escape.csv','a//b.csv','script.py','nested.zip'])
def test_reject_unsafe_archives_without_committing(repo,name):
 app.dependency_overrides[principal]=lambda:actor()
 with TestClient(app) as c:
  assert upload(c,[('safe.csv','x\n1'),(name,'x\n2')]).status_code==422
 assert submissions.history(repo)==[]
 assert repo.catalog()['files']==[]

def test_symlink_duplicate_and_pdf_deferred(repo):
 app.dependency_overrides[principal]=lambda:actor()
 with TestClient(app) as c:
  info=zipfile.ZipInfo('link.csv');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
  assert upload(c,[(info,'/etc/passwd')]).status_code==422
  assert upload(c,[('a.csv','x\n1'),('A.csv','x\n2')]).status_code==422
  r=upload(c,[('scan.pdf',b'%PDF-synthetic'),('a.csv','value\n12')]);assert r.status_code==201
  assert r.json()['pending_extraction']==1
  files=c.get('/api/analytics/catalog').json()['files'];assert sum(f['supported'] for f in files)==1
  assert upload(c,[('a.csv','x\n1')],cadence='annual').status_code==422
  assert upload(c,[('a.csv','x\n1')],period='2026-99-99').status_code==422

@pytest.mark.parametrize('cadence,period,end',[('daily','2024-02-29','2024-03-01'),('monthly','2026-12','2027-01-01'),('quarterly','2026-Q4','2027-01-01'),('half-yearly','2026-H2','2027-01-01'),('annual','2026','2027-01-01')])
def test_period_boundaries(cadence,period,end):assert submissions.period_bounds(cadence,period)[1].isoformat()==end

def test_no_fake_last_update(repo):
 s=submissions.schedules(repo,'BCCL',datetime(2026,9,4,tzinfo=submissions.TZ))
 for family in s['subsidiaries']['BCCL'].values():
  assert family['last_update'] is None
  assert all(c['status']=='awaiting_submission' for c in family['cycles'].values())

def test_csv_package_with_readme_and_macos_metadata(repo):
 app.dependency_overrides[principal]=lambda:actor()
 with TestClient(app) as c:
  result=upload(c,[('CIL_CSV/data.csv','mine,tonnes\nBCCL,120\n'),('CIL_CSV/README.md','# Source notes'),('__MACOSX/CIL_CSV/._README.md','metadata'),('CIL_CSV/.DS_Store','metadata')])
  assert result.status_code==201,result.text
  record=result.json()
  assert len(record['files'])==2 and record['pending_extraction']==0
  assert record['files'][1]['status']=='supporting_document'
  assert (repo.root/record['data_prefix']/'CIL_CSV/README.md').read_text()=='# Source notes'
  catalog=c.get('/api/analytics/catalog').json()['files']
  assert sum(f['supported'] for f in catalog)==1
  assert upload(c,[('README.md','Only notes')]).status_code==422
  bad=upload(c,[('data.csv','value\n1'),('scripts/run.exe','binary')])
  assert bad.status_code==422 and 'scripts/run.exe' in bad.json()['detail']

def test_report_revision_chains_and_entity_access(repo):
 from uuid import uuid4
 series='series-test';one=str(uuid4());two=str(uuid4())
 first=repo.root/'BCCL/production_offtake/report_generated'/one;first.mkdir();(first/'report.md').write_text('v1')
 r1=repo.next_report_revision(series);repo.register_report('author',one,first,'Report',r1)
 second=repo.root/'BCCL/production_offtake/report_generated'/two;second.mkdir();(second/'report.md').write_text('v2')
 r2=repo.next_report_revision(series);repo.register_report('author',two,second,'Report',r2)
 assert r2['version']==2 and r2['previous_id']==one
 with TestClient(app) as c:
  app.dependency_overrides[principal]=lambda:actor('BCCL')
  assert len(c.get('/api/analytics/reports').json())==2
  assert c.get('/api/analytics/reports/'+one+'/report.md').text=='v1'
  app.dependency_overrides[principal]=lambda:actor('SECL')
  assert c.get('/api/analytics/reports').json()==[]
  assert c.get('/api/analytics/reports/'+one+'/report.md').status_code==404
  app.dependency_overrides[principal]=lambda:actor('CMPDI','cmpdi')
  assert c.get('/api/analytics/reports').json()==[]
  assert c.get('/api/analytics/reports/'+one+'/report.md').status_code==404
