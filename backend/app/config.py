"""Central configuration, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Vultr Serverless Inference (OpenAI-compatible). Required for all LLM calls.
    vultr_inference_api_key: str = ""
    vultr_inference_base_url: str = "https://api.vultrinference.com/v1"
    vultr_model: str = "llama-3.3-70b-instruct"

    # Agent
    max_attempts: int = 4

    # Sandbox containment knobs
    sandbox_image: str = "sandbox-runner:latest"
    sandbox_timeout_seconds: int = 15
    sandbox_memory: str = "256m"
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 128

    # Server
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
