from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gateway_url: str = "https://aws-us-east-1.hevlayer.com"
    gateway_api_key: str = ""
    namespace: str = "wiki-simple"
    timeout_seconds: float = 30.0

    # Keep environment names identical across the Python backend and indexer.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_prefix="LAYER_",
    )
