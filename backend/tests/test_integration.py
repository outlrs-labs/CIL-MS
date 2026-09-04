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
