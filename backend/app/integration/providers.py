"""Encrypted local, shared CMPDI model configuration. Public responses never contain keys."""
import base64
import hashlib
import ipaddress
import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from cryptography.fernet import Fernet
from fastapi import HTTPException
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,SecretStr
from ..config import settings

class ProviderInput(BaseModel):
 model_config=ConfigDict(extra='forbid')
 name:str=Field(min_length=2,max_length=70)
 endpoint:str
 models:list[str]=Field(min_length=1,max_length=20)
 api_key:SecretStr=SecretStr('')
 api_base:str=''
 api_version:str=''
 role:Literal['standard','primary','fallback']='standard'
 timeout_seconds:int=Field(default=30,ge=5,le=120)

def cipher(secret):return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
def read_providers(path,secret):
 if not path.exists():return []
 return json.loads(cipher(secret).decrypt(path.read_bytes()))
def location():return settings().cil_processing_root/'private'/'model-providers.enc'
def public_config(c):return {k:v for k,v in c.items() if k!='api_key'}
def all_providers():
 return read_providers(location(),settings().df_bridge_secret.get_secret_value())
def validate_provider(data):
 if data.endpoint not in ('openai','azure','anthropic','gemini','sarvam','ollama','compatible'):raise HTTPException(422,'Select a supported provider.')
 if any(not m.strip() or len(m)>150 for m in data.models):raise HTTPException(422,'Enter valid model identifiers.')
 if data.endpoint!='ollama' and not data.api_key.get_secret_value().strip():raise HTTPException(422,'An API key is required.')
 if data.endpoint in ('azure','compatible','ollama') and not data.api_base:raise HTTPException(422,'This provider needs an API base URL.')
 if data.endpoint=='azure' and not data.api_version:raise HTTPException(422,'Azure needs an API version.')
 if data.api_base:
  url=urlparse(data.api_base)
  if url.username or url.password or url.query or url.fragment or not url.hostname:raise HTTPException(422,'Enter a base URL without credentials, query or fragment.')
  try: port=url.port
  except ValueError:raise HTTPException(422,'Invalid provider port.') from None
  local_ollama=data.endpoint=='ollama' and url.hostname in ('localhost','127.0.0.1','::1') and port==11434
  if not local_ollama:
   if url.scheme!='https':raise HTTPException(422,'Use HTTPS for remote model providers.')
   try:addresses=socket.getaddrinfo(url.hostname,port or 443,type=socket.SOCK_STREAM)
   except OSError:raise HTTPException(422,'Model provider hostname could not be resolved.') from None
   if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise HTTPException(422,'Private model endpoints are restricted to local Ollama on port 11434.')
  elif url.scheme not in ('http','https'):raise HTTPException(422,'Invalid Ollama URL.')
 return data

def add_provider(data):
 validate_provider(data);items=all_providers()
 if len(items)>=30:raise HTTPException(422,'Provider limit reached; remove unused configurations.')
 runtime_endpoint='openai' if data.endpoint in ('compatible','sarvam') else data.endpoint
 api_base=(data.api_base or ('https://api.sarvam.ai/v1' if data.endpoint=='sarvam' else '')).rstrip('/')
 item={'id':str(uuid4()),'name':data.name,'endpoint':runtime_endpoint,'kind':data.endpoint,'models':[m.strip() for m in data.models],'api_key':data.api_key.get_secret_value(),'api_base':api_base,'api_version':data.api_version,'role':data.role,'timeout_seconds':data.timeout_seconds}
 items.append(item);save(items);return public_config(item)
def save(items):
 path=location();path.parent.mkdir(parents=True,exist_ok=True);path.parent.chmod(0o700)
 temp=path.with_suffix('.tmp')
 with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as f:f.write(cipher(settings().df_bridge_secret.get_secret_value()).encrypt(json.dumps(items).encode()))
 os.replace(temp,path)
