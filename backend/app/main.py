from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID
import httpx
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from .auth import Principal, principal, member, admin, gateway
from .config import settings
from .gateway import Gateway

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        app.state.http = client
        from .integration.api import repository
        from .integration import ocr
        repo=repository()
        # A hard restart cannot leave a document permanently "running".
        for job in ocr.list_jobs(repo):
            if job['status'] in ('queued','running'):
                job.update(status='failed',error='Extraction interrupted by backend restart. Run again to create a new extraction revision.')
                ocr.save(repo,job)
        yield

app = FastAPI(title='CIL Central API', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().origins, allow_credentials=False,
                   allow_methods=['GET','POST','PATCH','DELETE'], allow_headers=['Authorization','Content-Type'])

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo submitted passwords or other request input in validation errors.
    return JSONResponse(status_code=422,content={'detail':'Invalid input. Check email, entity, field lengths and password requirements.'})

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class NewMember(StrictModel):
    email: EmailStr
    full_name: str = Field(min_length=2,max_length=100)
    entity_id: UUID
    temporary_password: SecretStr

    @field_validator('temporary_password')
    @classmethod
    def strong_password(cls, value):
        if len(value.get_secret_value()) < 14 or len(value.get_secret_value()) > 128:
            raise ValueError('Use a password between 14 and 128 characters.')
        return value

class ActivePatch(StrictModel):
    active: bool

class EntityInput(StrictModel):
    code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{1,15}$')
    name: str = Field(min_length=2,max_length=160)
    location: str = Field(default='',max_length=100)
    active: bool = True

class PasswordChange(StrictModel):
    current_password: SecretStr
    new_password: SecretStr

    @field_validator('new_password')
    @classmethod
    def strong_password(cls, value):
        return NewMember.strong_password(value)

@app.get('/health')
async def health():
    return {'status':'ok','configured':settings().ready}

@app.get('/api/me')
async def me(p: Principal = Depends(principal)):
    permissions = {'cil_admin':['entities.manage','members.manage','group.approve'],
                   'cmpdi':['entities.read','technical.coordinate'], 'subsidiary':['own_entity.read']}[p.profile['role']]
    return {'profile':p.profile,'entity':p.entity,'permissions':permissions}

@app.get('/api/entities')
async def entities(p: Principal = Depends(member), db: Gateway = Depends(gateway)):
    return await db.rows('entities',p.token,select='*',order='code.asc')

@app.get('/api/admin/users')
async def users(p: Principal = Depends(admin), db: Gateway = Depends(gateway)):
    return await db.rows('profiles',p.token,select='*',order='created_at.desc',limit='1000')

@app.get('/api/admin/events')
async def events(p: Principal = Depends(admin), db: Gateway = Depends(gateway)):
    return await db.rows('access_events',p.token,select='*',order='created_at.desc',limit='20')

@app.post('/api/admin/users',status_code=201)
async def create_member(data: NewMember,p: Principal = Depends(admin),db: Gateway = Depends(gateway)):
    rows = await db.rows('entities',p.token,id=f'eq.{data.entity_id}',select='*')
    if not rows or rows[0]['kind']=='holding' or not rows[0]['active']:
        raise HTTPException(422,'Select an active operating subsidiary or CMPDI. No additional administrator is allowed.')
    user = await db.request('POST','/auth/v1/admin/users',service=True,body={
        'email':str(data.email).lower(),'password':data.temporary_password.get_secret_value(),'email_confirm':True})
    uid = user['id']
    try:
        await db.rpc('provision_member',{'p_actor':p.id,'p_user_id':uid,'p_name':data.full_name,'p_entity':str(data.entity_id)})
    except HTTPException:
        # Retain the unassigned Auth user on ambiguous failure. Never delete a user
        # that a committed RPC may already have provisioned. No profile = no access.
        raise HTTPException(503,'Account setup needs review. Do not retry blindly; check the Auth user and profile in Supabase.') from None
    return {'id':uid,'message':'Account created. Share the temporary password securely; it must be changed at first sign-in.'}

@app.patch('/api/admin/users/{user_id}')
async def set_active(user_id: UUID,data: ActivePatch,p: Principal = Depends(admin),db: Gateway = Depends(gateway)):
    if str(user_id)==p.id:
        raise HTTPException(409,'The singleton administrator cannot be disabled.')
    await db.rpc('set_member_active',{'p_actor':p.id,'p_user_id':str(user_id),'p_active':data.active})
    return {'ok':True}

@app.post('/api/admin/entities',status_code=201)
async def create_entity(data: EntityInput,p: Principal = Depends(admin),db: Gateway = Depends(gateway)):
    uid = await db.rpc('save_entity',{'p_actor':p.id,'p_entity':None,'p_code':data.code,'p_name':data.name,'p_location':data.location,'p_active':data.active})
    return {'id':uid}

@app.patch('/api/admin/entities/{entity_id}')
async def edit_entity(entity_id: UUID,data: EntityInput,p: Principal = Depends(admin),db: Gateway = Depends(gateway)):
    rows = await db.rows('entities',p.token,id=f'eq.{entity_id}',select='*')
    if not rows or rows[0]['code']!=data.code or rows[0]['kind']=='holding':
        raise HTTPException(409,'The holding entity and entity codes are protected.')
    await db.rpc('save_entity',{'p_actor':p.id,'p_entity':str(entity_id),'p_code':data.code,'p_name':data.name,'p_location':data.location,'p_active':data.active})
    return {'ok':True}

@app.post('/api/auth/change-password')
async def change_password(data: PasswordChange,p: Principal = Depends(principal),db: Gateway = Depends(gateway)):
    if data.current_password.get_secret_value()==data.new_password.get_secret_value():
        raise HTTPException(422,'Choose a different password.')
    # Verify current password before clearing the first-login gate. The role is
    # always read from profiles, never editable auth user_metadata.
    session = await db.request('POST','/auth/v1/token',params={'grant_type':'password'},body={
        'email':p.profile['email'],'password':data.current_password.get_secret_value()})
    if session.get('user',{}).get('id')!=p.id:
        raise HTTPException(403,'Account verification failed.')
    await db.request('PUT','/auth/v1/user',token=session['access_token'],body={'password':data.new_password.get_secret_value()})
    await db.rpc('finish_password_change',{'p_user_id':p.id})
    return {'ok':True,'message':'Password changed. Sign in again with your new password.'}

from .integration.api import router as integration_router
app.include_router(integration_router)
