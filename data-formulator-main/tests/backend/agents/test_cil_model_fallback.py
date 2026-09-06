from data_formulator.agents.client_utils import Client


def test_cil_client_uses_gemini_when_primary_fails_before_stream(monkeypatch):
    client = Client(
        'openai',
        'primary-model',
        api_key='primary-test-key',
        fallback_configs=[{
            'endpoint': 'gemini',
            'model': 'fallback-model',
            'api_key': 'fallback-test-key',
        }],
    )
    attempts = []

    def dispatch(current, **_kwargs):
        attempts.append(current.endpoint)
        if current.endpoint == 'openai':
            raise RuntimeError('primary unavailable')
        return iter(['fallback-response'])

    monkeypatch.setattr(Client, '_dispatch', dispatch)
    assert list(client.get_completion([{'role': 'user', 'content': 'test'}], stream=True)) == ['fallback-response']
    assert attempts == ['openai', 'gemini']
