"""
Client for Vultr Serverless Inference (OpenAI-compatible Chat Completions).

All agent LLM calls in this project go through here — never from inside the
sandbox. The API key lives only in this process.
"""
import json

import httpx

from .config import get_settings


class InferenceError(RuntimeError):
    pass


class VultrInference:
    def __init__(self) -> None:
        s = get_settings()
        if not s.vultr_inference_api_key:
            raise InferenceError(
                "VULTR_INFERENCE_API_KEY is not set. Add it to your .env "
                "(get one from the Vultr console → Serverless → Inference)."
            )
        self.model = s.vultr_model
        self.base_url = s.vultr_inference_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {s.vultr_inference_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(90.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        """Return the assistant message content for a chat completion."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise InferenceError(f"Could not reach Vultr Inference: {exc}") from exc

        if resp.status_code >= 400:
            raise InferenceError(
                f"Vultr Inference returned {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise InferenceError(
                f"Unexpected response shape from Vultr Inference: {resp.text[:500]}"
            ) from exc
