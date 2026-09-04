import pytest
from fastapi import HTTPException
from app.integration.providers import ProviderInput,validate_provider,cipher,read_providers,public_config
import json

def test_provider_credentials_encrypted_and_redacted(tmp_path):
 secret='synthetic-test-secret-not-a-real-credential'
 config={'id':'fixture','api_key':'synthetic-key','models':['test-model']}
 path=tmp_path/'providers.enc';path.write_bytes(cipher(secret).encrypt(json.dumps([config]).encode()))
 assert b'synthetic-key' not in path.read_bytes()
 assert read_providers(path,secret)==[config]
 assert 'api_key' not in public_config(config)

@pytest.mark.parametrize('url',['http://169.254.169.254','https://localhost/v1','https://example.com:bad/v1'])
def test_unsafe_or_invalid_provider_endpoint_rejected(url):
 with pytest.raises(HTTPException) as error:
  validate_provider(ProviderInput(name='Test',endpoint='compatible',models=['test'],api_key='synthetic',api_base=url))
 assert error.value.status_code==422

def test_local_ollama_and_third_party_validation():
 assert validate_provider(ProviderInput(name='Local',endpoint='ollama',models=['test'],api_base='http://localhost:11434'))
 with pytest.raises(HTTPException):validate_provider(ProviderInput(name='Third party',endpoint='compatible',models=['test'],api_key='synthetic'))
