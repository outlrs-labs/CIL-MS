from fastapi.testclient import TestClient
from app.main import app
from app.auth import Principal, principal, gateway

ENTITY={'id':'10000000-0000-0000-0000-000000000000','code':'CIL','name':'Coal India Limited','kind':'holding','parent_id':None,'location':'Kolkata','active':True}
PROFILE={'id':'20000000-0000-0000-0000-000000000000','email':'admin@example.com','full_name':'CIL Administrator','role':'cil_admin','entity_id':ENTITY['id'],'active':True,'must_change_password':False,'created_at':'2026-01-01T00:00:00Z'}

def person(role='cil_admin'):
 p={**PROFILE,'role':role,'entity_id':ENTITY['id']}
 return Principal(p['id'],'test-token',p,ENTITY)

class FakeGateway:
 def __init__(self): self.calls=[]
 async def rows(self,table,token,**params):
  self.calls.append(('rows',table,params))
  if table=='entities': return [{**ENTITY,'id':'30000000-0000-0000-0000-000000000000','code':'BCCL','kind':'operating'}]
  return []
 async def request(self,method,path,**kwargs):
  self.calls.append(('request',method,path,kwargs))
  return {'id':'40000000-0000-0000-0000-000000000000'}
 async def rpc(self,name,data): self.calls.append(('rpc',name,data)); return data.get('p_user_id','ok')

def test_health_does_not_expose_configuration_values():
 with TestClient(app) as client:
  result=client.get('/health')
  assert result.status_code==200
  assert set(result.json())=={'status','configured'}

def test_me_derives_role_from_server_principal():
 app.dependency_overrides[principal]=lambda:person()
 try:
  with TestClient(app) as client:
   result=client.get('/api/me')
  assert result.status_code==200
  assert result.json()['profile']['role']=='cil_admin'
 finally: app.dependency_overrides.clear()

def test_non_admin_cannot_read_admin_directory():
 app.dependency_overrides[principal]=lambda:person('subsidiary')
 try:
  with TestClient(app) as client:
   result=client.get('/api/admin/users')
  assert result.status_code==403
 finally: app.dependency_overrides.clear()

def test_create_member_has_no_client_role_and_does_not_echo_password():
 fake=FakeGateway();app.dependency_overrides[principal]=lambda:person();app.dependency_overrides[gateway]=lambda:fake
 body={'email':'user@example.com','full_name':'Test User','entity_id':'30000000-0000-0000-0000-000000000000','temporary_password':'An-example-secret-123!','role':'cil_admin'}
 try:
  with TestClient(app) as client:
   result=client.post('/api/admin/users',headers={'Authorization':'Bearer x'},json=body)
  assert result.status_code==422
  assert 'An-example-secret-123!' not in result.text
 finally: app.dependency_overrides.clear()

def test_admin_cannot_assign_member_to_holding_entity():
 class HoldingGateway(FakeGateway):
  async def rows(self,*a,**k): return [ENTITY]
 fake=HoldingGateway();app.dependency_overrides[principal]=lambda:person();app.dependency_overrides[gateway]=lambda:fake
 body={'email':'user@example.com','full_name':'Test User','entity_id':ENTITY['id'],'temporary_password':'An-example-secret-123!'}
 try:
  with TestClient(app) as client:
   result=client.post('/api/admin/users',headers={'Authorization':'Bearer x'},json=body)
  assert result.status_code==422
  assert not any(c[0]=='request' for c in fake.calls)
 finally: app.dependency_overrides.clear()

def test_missing_bearer_is_rejected():
 with TestClient(app) as client:
  assert client.get('/api/me').status_code==401

def test_temporary_password_blocks_workspace():
 p=person();p.profile['must_change_password']=True
 app.dependency_overrides[principal]=lambda:p
 try:
  with TestClient(app) as client:
   assert client.get('/api/me').status_code==200
   assert client.get('/api/entities').status_code==403
 finally: app.dependency_overrides.clear()

def test_disabled_profile_rejected_even_with_valid_auth_user():
 class DisabledGateway(FakeGateway):
  async def request(self,*a,**k): return {'id':PROFILE['id'],'email_confirmed_at':'2026-01-01','user_metadata':{'role':'cil_admin'}}
  async def rows(self,*a,**k): return [{**PROFILE,'active':False}]
 app.dependency_overrides[gateway]=lambda:DisabledGateway()
 try:
  with TestClient(app) as client:
   assert client.get('/api/me',headers={'Authorization':'Bearer test'}).status_code==403
 finally: app.dependency_overrides.clear()

def test_successful_provision_uses_authenticated_actor_and_entity():
 fake=FakeGateway();app.dependency_overrides[principal]=lambda:person();app.dependency_overrides[gateway]=lambda:fake
 body={'email':'user@example.com','full_name':'Test User','entity_id':'30000000-0000-0000-0000-000000000000','temporary_password':'An-example-secret-123!'}
 try:
  with TestClient(app) as client:
   result=client.post('/api/admin/users',json=body)
  assert result.status_code==201
  call=next(c for c in fake.calls if c[0]=='rpc')
  assert call[1]=='provision_member'
  assert call[2]['p_actor']==PROFILE['id']
  assert call[2]['p_entity']==body['entity_id']
  assert 'An-example-secret-123!' not in result.text
 finally: app.dependency_overrides.clear()
