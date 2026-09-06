import asyncio
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import Principal,principal
from app.integration.repository import Repository,PRODUCTION,TECHNICAL
from app.integration import api

@pytest.fixture
def repo(tmp_path,monkeypatch):
 r=Repository(tmp_path/'cil',tmp_path/'processing');r.initialize()
 monkeypatch.setattr(api,'repository',lambda:r)
 yield r
 app.dependency_overrides.clear()

def as_role(role):
 entity={'id':'entity','kind':'technical' if role=='cmpdi' else 'operating','active':True}
 return Principal('test-user','test-token',{'id':'test-user','role':role,'active':True,'must_change_password':False},entity)

def test_folder_architecture_and_output_exclusion(repo):
 assert len(repo.catalog()['folders'])==7*5+6
 assert len(list(repo.root.glob('*/*/data')))==41
 source=repo.root/'BCCL/production_offtake/data/month.csv';source.write_text('value\n12\n')
 (repo.root/'BCCL/production_offtake/report_generated/old.csv').write_text('value\n999\n')
 assert len(repo.catalog()['files'])==1
 assert (repo.root/'CMPDI/annual/data').is_dir()
 assert (repo.root/'CMPDI/report').is_dir()

def test_snapshot_preserves_source_version_and_excludes_symlink(repo,tmp_path):
 source=repo.root/'BCCL/production_offtake/data/month.csv';source.write_text('value\n12\n')
 outside=tmp_path/'outside.csv';outside.write_text('private')
 (source.parent/'escape.csv').symlink_to(outside)
 entries=repo.catalog()['files'];assert len(entries)==1
 snap=repo.snapshot(entries[0],str(uuid4()))
 source.write_text('value\n15\n')
 assert (repo.processing/snap['snapshot']).read_text()=='value\n12\n'
 assert snap['sha256']==hashlib.sha256(b'value\n12\n').hexdigest()
 with pytest.raises(ValueError):repo.snapshot(entries[0],str(uuid4()))

@pytest.mark.parametrize('role',['cil_admin','subsidiary'])
def test_non_cmpdi_catalog_forbidden(repo,role):
 app.dependency_overrides[principal]=lambda:as_role(role)
 with TestClient(app) as c:assert c.get('/api/cmpdi/catalog').status_code==403

def test_analysis_owner_and_invalid_selection(repo):
 app.dependency_overrides[principal]=lambda:as_role('cmpdi')
 id=str(uuid4());repo.put_analysis({'id':id,'owner':'other','title':'private'})
 with TestClient(app) as c:
  assert c.get('/api/cmpdi/analyses/'+id).status_code==404
  assert c.post('/api/cmpdi/analyses',json={'title':'Bad selection','inputs':[{'file_id':'../outside.csv'}]}).status_code==422

def test_direct_analysis_file_is_persisted_and_catalogued(repo):
 app.dependency_overrides[principal]=lambda:as_role('cmpdi')
 with TestClient(app) as c:
  r=c.post('/api/analytics/session-source?entity=BCCL&family=production_offtake&name=shift.csv',content=b'mine,tonnes\nA,42\n',headers={'content-type':'application/octet-stream'})
  assert r.status_code==201
  item=r.json();assert item['session_upload'] is True and item['name']=='shift.csv'
  assert (repo.root/item['relative_path']).read_bytes()==b'mine,tonnes\nA,42\n'
  files=c.get('/api/analytics/catalog').json()['files']
  assert any(entry['id']==item['id'] for entry in files)
  assert c.post('/api/analytics/session-source?entity=BCCL&family=production_offtake&name=notes.exe',content=b'bad').status_code==422

def test_direct_scanned_document_is_catalogued_for_ocr(repo):
 app.dependency_overrides[principal]=lambda:as_role('cmpdi')
 with TestClient(app) as c:
  r=c.post('/api/analytics/session-source?entity=BCCL&family=production_offtake&name=scan.pdf',content=b'%PDF-1.4 demo',headers={'content-type':'application/pdf'})
  assert r.status_code==201
  item=r.json()
  assert item['supported'] is False
  assert item['extractable'] is True
  assert item['format']=='pdf'
  assert (repo.root/item['relative_path']).read_bytes()==b'%PDF-1.4 demo'

def test_analysis_time_ocr_imports_markdown_and_csv_derivatives(repo,monkeypatch):
 from unittest.mock import AsyncMock
 folder=repo.root/'BCCL/production_offtake/extractions/job-1';folder.mkdir(parents=True)
 markdown=folder/'reviewed-document.md';markdown.write_text('# Page 1\n\nProduction was 42 tonnes.\n')
 table=folder/'reviewed-page-1-table-1.csv';table.write_text('mine,tonnes\nA,42\n')
 def entry(path,format):
  relative=path.relative_to(repo.root).as_posix();stat=path.stat()
  return {'id':hashlib.sha256(f'{relative}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest(),'entity':'BCCL','family':'production_offtake','name':'scan.pdf · '+path.name.removeprefix('reviewed-'),'relative_path':relative,'bytes':stat.st_size,'modified':stat.st_mtime,'supported':True,'extractable':False,'format':format,'submission_id':'submission-1','version':1,'cadence':'monthly','period':'2026-09','is_latest':True,'extraction_id':'job-1'}
 derivatives=[entry(markdown,'md'),entry(table,'csv')]
 monkeypatch.setattr(api.ocr,'ensure_for_analysis',AsyncMock(return_value={'id':'job-1'}))
 monkeypatch.setattr(api.ocr,'catalog_files',lambda *_:derivatives)
 upstream=AsyncMock(return_value={'tables':[{'id':'markdown-context'},{'id':'table-data'}]})
 monkeypatch.setattr(api,'upstream',upstream)
 original={'id':'pdf-id','entity':'BCCL','family':'production_offtake','name':'scan.pdf','relative_path':'BCCL/production_offtake/data/versions/monthly/2026-09/submission-1/scan.pdf','bytes':10,'modified':1,'supported':False,'extractable':True,'format':'pdf','submission_id':'submission-1','version':1,'cadence':'monthly','period':'2026-09','is_latest':True,'sha256':'source-hash'}
 value={'id':str(uuid4()),'owner':'test-user','title':'Scanned report','period':'2026-09','target_entity':'BCCL','target_family':'production_offtake','scope_entities':['BCCL'],'missing_entities':[],'created':1,'status':'importing','phase':'queued','sources':[],'tables':[]}
 asyncio.run(api.import_analysis(value,[(original,api.InputSelection(file_id='pdf-id'))]))
 saved=repo.get_analysis(value['id'],'test-user')
 assert saved['status']=='ready' and {Path(item['snapshot']).suffix for item in saved['sources']}=={'.md','.csv'}
 assert saved['document_context'][0]['source']=='scan.pdf'
 assert {Path(item['snapshot']).suffix for item in upstream.await_args.args[4]['sources']}=={'.md','.csv'}

def test_workbench_requires_session(repo):
 with TestClient(app) as c:assert c.get('/cmpdi/workbench/'+str(uuid4())+'/api/app-config').status_code==401

def test_cookie_is_httponly_and_bound_to_analysis(repo,monkeypatch):
 app.dependency_overrides[principal]=lambda:as_role('cmpdi')
 id=str(uuid4());repo.put_analysis({'id':id,'owner':'test-user','status':'ready'})
 with TestClient(app) as c:
  r=c.post('/api/cmpdi/analyses/'+id+'/workbench-session')
  assert r.status_code==200
  assert r.json()['expires_in']==api.WORKBENCH_SESSION_SECONDS
  assert f'Max-Age={api.WORKBENCH_SESSION_SECONDS}' in r.headers['set-cookie']
  assert 'HttpOnly' in r.headers['set-cookie']
  assert 'SameSite=strict' in r.headers['set-cookie']
  assert c.get('/cmpdi/workbench/'+str(uuid4())+'/api/app-config').status_code==401
  base=f'/cmpdi/workbench/{id}/'
  from unittest.mock import AsyncMock
  monkeypatch.setattr(api,'workbench_principal',AsyncMock(return_value=as_role('cmpdi')))
  page=c.get(base)
  assert page.status_code==200
  entry=re.search(r'<script[^>]+src="([^"]+\.js)"',page.text)
  assert entry and entry.group(1).startswith(base)
  assert c.get(entry.group(1)).status_code==200

def test_report_artifacts_and_library_preserve_provenance(repo,monkeypatch):
 import base64,zipfile
 from starlette.requests import Request
 from unittest.mock import AsyncMock
 id=str(uuid4());p=as_role('cmpdi')
 a={'id':id,'owner':p.id,'title':'Synthetic report','target_entity':'CMPDI','target_family':'annual','scope_entities':['BCCL'],'missing_entities':[],'period':'Synthetic','sources':[{'relative_path':'BCCL/production_offtake/data/test.csv','sha256':'fixture-hash'}]}
 image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nsynthetic-test').decode()
 payload=json.dumps({'content':'# Test\n![Chart](chart://test_chart)','png':image,'chart_images':{'test_chart':image}}).encode()
 async def receive():return {'type':'http.request','body':payload,'more_body':False}
 request=Request({'type':'http','method':'POST','headers':[]},receive)
 monkeypatch.setattr(api,'upstream',AsyncMock(return_value={'state':'fixture'}))
 saved=asyncio.run(api.save_report(request,p,a));folder=repo.root/saved['relative_path']
 assert 'charts/test_chart.png' in (folder/'report.md').read_text()
 assert 'fixture-hash' in (folder/'report.md').read_text()
 with zipfile.ZipFile(folder/'report.zip') as archive:assert 'charts/test_chart.png' in archive.namelist()
 assert (repo.root/'CMPDI/report'/saved['id']/'report.zip').read_bytes()==(folder/'report.zip').read_bytes()
 assert repo.reports(p.id)[0]['id']==saved['id']
 with pytest.raises(Exception):repo.report_path(saved['id'],'another-user')

def test_direct_report_can_be_generated_and_sent_through_simple_audit(repo):
 source=repo.root/'BCCL/production_offtake/data/shift.csv'
 source.write_text('mine,production,offtake\nA,100,85\nB,120,105\n')
 app.dependency_overrides[principal]=lambda:as_role('cmpdi')
 with TestClient(app) as c:
  files=c.get('/api/analytics/catalog?include_history=true').json()['files']
  selected=next(item for item in files if item['name']=='shift.csv')
  result=c.post('/api/analytics/reports/generate',json={
   'title':'Production summary','period':'September 2026',
   'scope_entities':['BCCL'],'target_entity':'BCCL','target_family':'production_offtake',
   'inputs':[{'file_id':selected['id']}],'send_for_audit':False,
  })
  assert result.status_code==201
  report=result.json()
  assert report['audit_status'] is None
  invalid=c.post(f"/api/analytics/reports/{report['id']}/audit",json={'category':'annual'})
  assert invalid.status_code==422
  submitted=c.post(f"/api/analytics/reports/{report['id']}/audit",json={'category':'financial'})
  assert submitted.status_code==201 and submitted.json()['status']=='pending_review'
  assert c.get('/api/analytics/audits').json()==[]
  assert all(item['id']!=report['id'] for item in c.get('/api/analytics/reports').json())
  assert c.get(f"/api/analytics/reports/{report['id']}/report.pdf").status_code==404
  assistant=Principal('assistant','token',{'id':'assistant','role':'subsidiary','review_position':'assistant_manager','active':True,'must_change_password':False},{'id':'entity','code':'BCCL','kind':'operating','active':True})
  app.dependency_overrides[principal]=lambda:assistant
  queue=c.get('/api/analytics/audits').json()
  assert [item['report_id'] for item in queue]==[report['id']]
  assert queue[0]['category']=='financial' and queue[0]['version']==1
  assert c.get('/api/analytics/reports').json()==[]
  reviewed=c.post(f"/api/analytics/audits/{report['id']}/decision",json={'decision':'await','comment':'Confirm units'})
  assert reviewed.status_code==200 and reviewed.json()['status']=='awaiting'
  reviewer=Principal('reviewer','token',{'id':'reviewer','role':'subsidiary','review_position':'manager','active':True,'must_change_password':False},{'id':'entity','code':'BCCL','kind':'operating','active':True})
  app.dependency_overrides[principal]=lambda:reviewer
  pdf=c.get(f"/api/analytics/reports/{report['id']}/report.pdf")
  assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
  approved=c.post(f"/api/analytics/audits/{report['id']}/decision",json={'decision':'approve','comment':'Checked'})
  assert approved.status_code==200 and approved.json()['status']=='submitted_to_cmpdi'
  assert c.get('/api/analytics/audits').json()==[]
  subsidiary_submissions=c.get('/api/analytics/reports').json()
  assert [item['id'] for item in subsidiary_submissions]==[report['id']]
  app.dependency_overrides[principal]=lambda:as_role('cmpdi')
  submissions=c.get('/api/analytics/reports').json()
  final=next(item for item in submissions if item['id']==report['id'])
  assert final['audit_status']=='submitted_to_cmpdi' and final['family']=='financial'
  assert c.get('/api/analytics/audits').json()==[]
  assert c.get(f"/api/analytics/reports/{report['id']}/report.pdf").status_code==200

@pytest.mark.parametrize('position',['assistant_manager','manager'])
def test_authorized_manager_positions_can_approve_an_audit(repo,position):
 report_id=str(uuid4());folder=repo.root/'BCCL/production_offtake/report_generated'/report_id;folder.mkdir(parents=True);(folder/'report.md').write_text('review me')
 repo.register_report('author',report_id,folder,'Approval test',repo.next_report_revision('approval-'+position))
 repo.submit_audit(report_id,'author','BCCL','production_offtake')
 result=repo.decide_audit(report_id,'reviewer-'+position,position,'approve','Checked')
 assert result['status']=='submitted_to_cmpdi'
 assert result['assistant_reviewer' if position=='assistant_manager' else 'manager_reviewer']=='reviewer-'+position
