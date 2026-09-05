import asyncio
import hashlib
import json
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

def test_workbench_requires_session(repo):
 with TestClient(app) as c:assert c.get('/cmpdi/workbench/'+str(uuid4())+'/api/app-config').status_code==401

def test_cookie_is_httponly_and_bound_to_analysis(repo):
 app.dependency_overrides[principal]=lambda:as_role('cmpdi')
 id=str(uuid4());repo.put_analysis({'id':id,'owner':'test-user','status':'ready'})
 with TestClient(app) as c:
  r=c.post('/api/cmpdi/analyses/'+id+'/workbench-session')
  assert r.status_code==200
  assert 'HttpOnly' in r.headers['set-cookie']
  assert 'SameSite=strict' in r.headers['set-cookie']
  assert c.get('/cmpdi/workbench/'+str(uuid4())+'/api/app-config').status_code==401

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
  forbidden=c.post(f"/api/analytics/audits/{report['id']}/decision",json={'decision':'approve','comment':'Checked'})
  assert forbidden.status_code==403
  reviewer=Principal('reviewer','token',{'id':'reviewer','role':'subsidiary','review_position':'manager','active':True,'must_change_password':False},{'id':'entity','code':'BCCL','kind':'operating','active':True})
  app.dependency_overrides[principal]=lambda:reviewer
  pdf=c.get(f"/api/analytics/reports/{report['id']}/report.pdf")
  assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
  awaiting=c.post(f"/api/analytics/audits/{report['id']}/decision",json={'decision':'await','comment':'Confirm units'})
  assert awaiting.status_code==200 and awaiting.json()['status']=='awaiting'
  approved=c.post(f"/api/analytics/audits/{report['id']}/decision",json={'decision':'approve','comment':'Checked'})
  assert approved.status_code==200 and approved.json()['status']=='submitted_to_cmpdi'
  app.dependency_overrides[principal]=lambda:as_role('cmpdi')
  submissions=c.get('/api/analytics/reports').json()
  final=next(item for item in submissions if item['id']==report['id'])
  assert final['audit_status']=='submitted_to_cmpdi' and final['family']=='financial'
  assert c.get('/api/analytics/audits').json()==[]
  assert c.get(f"/api/analytics/reports/{report['id']}/report.pdf").status_code==200
