import os
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import Principal,principal
from app.integration import api,submissions,vault
from app.integration.repository import Repository

@pytest.fixture
def client(tmp_path,monkeypatch):
 r=Repository(tmp_path/'cil',tmp_path/'processing');r.initialize();submissions.initialize(r);submissions.publish_schedule(r)
 for code in ('BCCL','SECL'):
  folder=r.root/code/'production_offtake/data/2026/September';folder.mkdir(parents=True)
  (folder/'production.csv').write_text('mine,tonnes\nA,123\n')
  (folder/'notes.md').write_text('Source notes')
  (folder/'archive.zip').write_bytes(b'fixture')
 monkeypatch.setattr(api,'repository',lambda:r)
 def login(code='BCCL',role='subsidiary'):
  app.dependency_overrides[principal]=lambda:Principal('vault-user','fixture',{'role':role,'active':True,'must_change_password':False},{'code':code,'active':True})
 login()
 with TestClient(app) as c:yield c,r,login
 app.dependency_overrides.clear()

def test_nested_folders_download_and_scope(client):
 c,r,login=client
 root=c.get('/api/analytics/vault').json()
 assert [e['name'] for e in root['entries']]==['BCCL','reporting_schedule.json']
 folder='BCCL/production_offtake/data/2026/September'
 listing=c.get('/api/analytics/vault',params={'path':folder}).json()
 assert [e['name'] for e in listing['entries']]==['archive.zip','notes.md','production.csv']
 download=c.get('/api/analytics/vault/file',params={'path':folder+'/production.csv'})
 assert download.status_code==200 and 'A,123' in download.text
 assert download.headers['content-disposition'].startswith('attachment')
 assert c.get('/api/analytics/vault',params={'path':'SECL'}).status_code==404
 assert c.get('/api/analytics/vault/file',params={'path':folder.replace('BCCL','SECL')+'/production.csv'}).status_code==404
 schedule=c.get('/api/analytics/vault/file',params={'path':'reporting_schedule.json'}).json()
 assert list(schedule['subsidiaries'])==['BCCL']
 login('CMPDI','cmpdi')
 assert len(c.get('/api/analytics/vault').json()['entries'])==9
 assert c.get('/api/analytics/vault',params={'path':'SECL'}).status_code==200
 login('CIL','cil_admin')
 admin=c.get('/api/analytics/vault')
 assert admin.status_code==200 and len(admin.json()['entries'])==9

def test_filters_search_sort_and_pages(client):
 c,r,_=client
 result=c.get('/api/analytics/vault',params={'kind':'tables','q':'production'}).json()
 assert result['recursive'] and len(result['entries'])==1
 assert result['entries'][0]['name']=='production.csv'
 folder=r.root/'BCCL/production_offtake/data/2026/September'
 old=time.time()-100*86400;os.utime(folder/'production.csv',(old,old))
 assert not c.get('/api/analytics/vault',params={'kind':'tables','q':'production','days':7}).json()['entries']
 assert c.get('/api/analytics/vault',params={'kind':'documents'}).json()['entries'][0]['name']=='notes.md'
 assert c.get('/api/analytics/vault',params={'kind':'invalid'}).status_code==422
 for i in range(205):(folder/f'{i:03}.csv').write_text('x\n1')
 first=c.get('/api/analytics/vault',params={'path':str(folder.relative_to(r.root))}).json()
 assert len(first['entries'])==200 and first['next_offset']==200
 second=c.get('/api/analytics/vault',params={'path':str(folder.relative_to(r.root)),'offset':200}).json()
 assert len(second['entries'])==8 and second['next_offset'] is None
 assert not {e['path'] for e in first['entries']}&{e['path'] for e in second['entries']}

def test_role_aware_subsidiary_and_report_filters(client):
 c,_,login=client
 own=c.get('/api/analytics/vault',params={'entity':'SECL','report':'production_offtake'}).json()
 assert own['entries'] and all(entry['path'].startswith('BCCL/production_offtake') for entry in own['entries'])
 assert own['filter_options']['entities']==['BCCL']
 login('CIL','cil_admin')
 filtered=c.get('/api/analytics/vault',params={'entity':'SECL','report':'production_offtake'}).json()
 assert filtered['entries'] and all(entry['path'].startswith('SECL/production_offtake') for entry in filtered['entries'])
 assert 'CMPDI' in filtered['filter_options']['entities']
 assert c.get('/api/analytics/vault',params={'entity':'SECL','report':'annual'}).status_code==422

def test_sort_directions(client):
 c,r,_=client
 folder=r.root/'BCCL/production_offtake/data/2026/September'
 old=time.time()-1000;os.utime(folder/'archive.zip',(old,old))
 newest=c.get('/api/analytics/vault',params={'path':str(folder.relative_to(r.root)),'sort':'modified'}).json()['entries']
 oldest=c.get('/api/analytics/vault',params={'path':str(folder.relative_to(r.root)),'sort':'modified_asc'}).json()['entries']
 assert newest[0]['modified']>=newest[-1]['modified']
 assert oldest[0]['name']=='archive.zip'
 descending=c.get('/api/analytics/vault',params={'path':str(folder.relative_to(r.root)),'sort':'name_desc'}).json()['entries']
 assert [entry['name'] for entry in descending]==sorted((entry['name'] for entry in descending),reverse=True)

@pytest.mark.parametrize('path',['../processing','/etc/passwd','BCCL/../SECL','BCCL//production_offtake','BCCL/.env','BCCL/production_offtake/data/.secret','BCCL/production_offtake/data/link.csv','BCCL/production_offtake/data/linked/production.csv'])
def test_unsafe_paths_and_links(client,path):
 c,r,_=client
 base=r.root/'BCCL/production_offtake/data'
 (base/'.secret').write_text('private')
 (base/'link.csv').symlink_to(r.root/'SECL/production_offtake/data/2026/September/production.csv')
 (base/'linked').symlink_to(r.root/'SECL/production_offtake/data/2026/September',target_is_directory=True)
 assert c.get('/api/analytics/vault',params={'path':path}).status_code==404
 assert c.get('/api/analytics/vault/file',params={'path':path}).status_code==404
 assert not any(e['name'] in ('.secret','link.csv','linked') for e in c.get('/api/analytics/vault',params={'path':'BCCL/production_offtake/data'}).json()['entries'])

def test_vault_is_read_only(client):
 c,repo,_=client
 source=repo.root/'BCCL/production_offtake/data/2026/September/production.csv'
 original=source.read_bytes()
 for route in ('folders','rename','move','delete','edit'):
  assert c.post('/api/analytics/vault/'+route,json={}).status_code==404
 assert source.read_bytes()==original
