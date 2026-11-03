"""Central configuration, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The README puts .env at the repo root; also accept one next to the backend
    # (later files win). Real env vars override both.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Vultr Serverless Inference (OpenAI-compatible). Required for all LLM calls.
    vultr_inference_api_key: str = ""
    vultr_inference_base_url: str = "https://api.vultrinference.com/v1"
    vultr_model: str = "llama-3.3-70b-instruct"

    # Agent
    max_attempts: int = 4
    # Public demo protection: cap simultaneous runs (each burns a container + LLM credits).
    max_concurrent_runs: int = 2

    # Sandbox containment knobs
    sandbox_image: str = "sandbox-runner:latest"
    sandbox_timeout_seconds: int = 15
    sandbox_memory: str = "256m"
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 128
    # Optional OCI runtime, e.g. "runsc" for gVisor kernel isolation. Empty = Docker default.
    sandbox_runtime: str = ""
    # Code is passed as an argv string; Linux caps a single arg at 128 KiB.
    max_code_bytes: int = 64_000

    # Server
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
