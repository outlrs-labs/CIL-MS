import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.gateway import Gateway


def test_identity_read_retries_a_transient_network_failure(monkeypatch):
    class Client:
        calls = 0

        async def request(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError('temporary DNS failure')
            return httpx.Response(200, json={'id': 'user-1'})

    async def no_delay(_seconds):
        return None

    monkeypatch.setattr('app.gateway.asyncio.sleep', no_delay)
    client = Client()
    config = Settings(
        supabase_url='https://example.supabase.co',
        supabase_publishable_key='public-key',
        supabase_secret_key='service-key',
    )

    result = asyncio.run(
        Gateway(client, config).request('GET', '/auth/v1/user', token='user-token')
    )

    assert result == {'id': 'user-1'}
    assert client.calls == 2


def test_mutating_identity_request_is_not_retried(monkeypatch):
    class Client:
        calls = 0

        async def request(self, *args, **kwargs):
            self.calls += 1
            raise httpx.ConnectError('offline')

    client = Client()
    config = Settings(
        supabase_url='https://example.supabase.co',
        supabase_publishable_key='public-key',
        supabase_secret_key='service-key',
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(Gateway(client, config).request('POST', '/rest/v1/profiles'))

    assert getattr(error.value, 'status_code', None) == 503
    assert client.calls == 1
