import httpx
from fastapi import HTTPException
from .config import Settings

class Gateway:
    """Auth validation uses the Auth server; user reads keep the caller's JWT and RLS."""
    def __init__(self, client: httpx.AsyncClient, config: Settings):
        self.client, self.config = client, config

    async def request(self, method, path, *, token=None, service=False, body=None, params=None):
        if not self.config.ready:
            raise HTTPException(503, 'Supabase is not configured. Complete the server environment first.')
        key = self.config.supabase_secret_key.get_secret_value() if service else self.config.supabase_publishable_key
        headers = {'apikey': key}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        elif service and key.startswith('eyJ'):
            headers['Authorization'] = f'Bearer {key}'
        try:
            response = await self.client.request(method, self.config.supabase_url + path, headers=headers, json=body, params=params)
        except httpx.RequestError:
            raise HTTPException(503, 'Identity service is unavailable. Please retry.') from None
        if not response.is_success:
            if path == '/auth/v1/user' and method == 'GET':
                raise HTTPException(401, 'Session expired or invalid. Sign in again.')
            if path.startswith('/auth/v1/token'):
                raise HTTPException(400, 'Current password could not be verified.')
            # Do not forward upstream errors: they may contain SQL, addresses or tokens.
            status = 409 if response.status_code in (400,409,422) else 503
            raise HTTPException(status, 'The operation could not be completed. Check the input, configuration, or existing account.')
        return response.json() if response.content else None

    async def rows(self, table, token, **params):
        return await self.request('GET', f'/rest/v1/{table}', token=token, params=params)

    async def rpc(self, name, data):
        return await self.request('POST', f'/rest/v1/rpc/{name}', service=True, body=data)
