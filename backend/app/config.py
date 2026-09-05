from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / '.env', extra='ignore')
    supabase_url: str = ''
    supabase_publishable_key: str = ''
    supabase_secret_key: SecretStr = SecretStr('')
    cors_origins: str = 'http://localhost:5173'
    admin_email: str = ''
    admin_password: SecretStr = SecretStr('')
    admin_name: str = 'CIL Administrator'
    admin_user_id: str = ''
    cil_data_root: Path = Path(__file__).resolve().parents[3] / 'Data' / 'cil'
    cil_processing_root: Path = Path(__file__).resolve().parents[3] / 'Data' / '.processing'
    df_url: str = 'http://127.0.0.1:5567'
    df_bridge_secret: SecretStr = SecretStr('')
    workbench_cookie_secure: bool = False

    @field_validator('supabase_url')
    @classmethod
    def safe_url(cls, value: str):
        value = value.rstrip('/')
        if value and not (value.startswith('https://') or value.startswith('http://127.0.0.1:') or value.startswith('http://localhost:')):
            raise ValueError('Use HTTPS for Supabase, except local development.')
        return value

    @property
    def ready(self):
        return bool(self.supabase_url and self.supabase_publishable_key and self.supabase_secret_key.get_secret_value())

    @property
    def origins(self):
        origins = [x.strip() for x in self.cors_origins.split(',') if x.strip()]
        if '*' in origins:
            raise ValueError('Explicit CORS origins required')
        # Local development is often opened through either loopback hostname.
        # Permit both while retaining explicit origins for deployed environments.
        for local in ('http://localhost:5173','http://127.0.0.1:5173'):
            if local not in origins:origins.append(local)
        return origins

@lru_cache
def settings():
    return Settings()
