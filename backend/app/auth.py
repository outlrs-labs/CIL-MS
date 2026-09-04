from dataclasses import dataclass
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .gateway import Gateway
from .config import settings

bearer = HTTPBearer(auto_error=False)

def gateway(request: Request):
    return Gateway(request.app.state.http, settings())

@dataclass
class Principal:
    id: str
    token: str
    profile: dict
    entity: dict

async def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Gateway = Depends(gateway)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Sign in to continue.', headers={'WWW-Authenticate':'Bearer'})
    user = await db.request('GET', '/auth/v1/user', token=credentials.credentials)
    try:
        uid = str(UUID(user['id']))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Invalid identity.') from None
    if not user.get('email_confirmed_at'):
        raise HTTPException(403, 'A confirmed account is required.')
    rows = await db.rows('profiles', credentials.credentials, id=f'eq.{uid}', select='*')
    if not rows or not rows[0]['active']:
        raise HTTPException(403, 'Your account has not been provisioned or has been disabled. Contact CIL administration.')
    p = rows[0]
    entities = await db.rows('entities', credentials.credentials, id=f'eq.{p["entity_id"]}', select='*')
    if not entities or not entities[0]['active']:
        raise HTTPException(403, 'Your entity is inactive. Contact CIL administration.')
    e = entities[0]
    if {'cil_admin':'holding','cmpdi':'technical','subsidiary':'operating'}.get(p['role']) != e['kind']:
        raise HTTPException(403, 'Invalid account assignment.')
    return Principal(uid, credentials.credentials, p, e)

async def member(p: Principal = Depends(principal)):
    if p.profile['must_change_password']:
        raise HTTPException(403, 'Change your temporary password before continuing.')
    return p

async def admin(p: Principal = Depends(member)):
    if p.profile['role'] != 'cil_admin':
        raise HTTPException(403, 'Only the CIL administrator can perform this action.')
    return p
