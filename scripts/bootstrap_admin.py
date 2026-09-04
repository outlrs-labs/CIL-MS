"""Explicit, local-only bootstrap. No public bootstrap HTTP endpoint."""
import asyncio
import sys
from pathlib import Path
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import httpx
from app.config import Settings
from app.gateway import Gateway
from fastapi import HTTPException

async def run():
    config=Settings()
    if not config.ready or not config.admin_email:
        raise SystemExit('Fill SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY and ADMIN_EMAIL in cil-platform/.env first.')
    async with httpx.AsyncClient(timeout=25) as client:
        db=Gateway(client,config)
        admins=await db.request('GET','/rest/v1/central_admin',service=True,params={'select':'user_id'})
        if admins:
            uid=admins[0]['user_id']
            user=await db.request('GET',f'/auth/v1/admin/users/{uid}',service=True)
            if user['email'].lower()!=config.admin_email.lower() or (config.admin_user_id and str(UUID(config.admin_user_id))!=uid):
                raise SystemExit('A different singleton administrator is already bound. Bootstrap refuses to replace it.')
            print('The configured singleton administrator already exists. No password or role changed.')
            return
        if config.admin_user_id:
            uid=str(UUID(config.admin_user_id))
            user=await db.request('GET',f'/auth/v1/admin/users/{uid}',service=True)
            if user['email'].lower()!=config.admin_email.lower() or not user.get('email_confirmed_at'):
                raise SystemExit('ADMIN_USER_ID must match the confirmed ADMIN_EMAIL account.')
        else:
            password=config.admin_password.get_secret_value()
            if not 14 <= len(password) <= 128:
                raise SystemExit('Set ADMIN_PASSWORD to a unique 14–128 character password.')
            user=await db.request('POST','/auth/v1/admin/users',service=True,body={
                'email':config.admin_email.lower(),'password':password,'email_confirm':True})
            uid=user['id']
        await db.rpc('bootstrap_admin',{'p_user_id':uid,'p_name':config.admin_name})
        print('Singleton CIL administrator provisioned. Sign in using the configured email and password.')
        print('Remove ADMIN_PASSWORD from .env after successful bootstrap. Never share the server secret key.')

if __name__=='__main__':
    try:
        asyncio.run(run())
    except HTTPException as exc:
        raise SystemExit(f'Bootstrap failed: {exc.detail} If an Auth account exists without a profile, explicitly set ADMIN_USER_ID and rerun. No credentials were printed.') from None
