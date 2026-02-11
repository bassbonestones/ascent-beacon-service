from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "Ascent Beacon API"
    env: str = "local"
    
    # Database
    database_url: str
    
    # Dev user (for testing)
    dev_user_id: str | None = None
    
    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_minutes: int = 43200  # 30 days
    
    # Magic Link
    magic_link_ttl_minutes: int = 5
    magic_link_base_url: str
    resend_api_key: str | None = None
    magic_link_from: str | None = None
    
    # LLM
    llm_provider: str = "openai"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    
    # STT
    stt_provider: str = "openai"
    stt_api_key: str | None = None
    stt_base_url: str = "https://api.openai.com/v1"
    stt_model: str = "whisper-1"
    
    # OAuth
    google_client_ids: str | None = None
    apple_audience: str | None = None
    apple_issuer: str = "https://appleid.apple.com"


settings = Settings()
