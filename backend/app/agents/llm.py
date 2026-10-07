"""Validated JSON completions through the configured LiteLLM proxy."""

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.config import Settings, settings

Output = TypeVar("Output", bound=BaseModel)


class LLMUnavailableError(RuntimeError):
    """Transient proxy/network failure that a background task may retry."""


class LLMOutputError(ValueError):
    """The model did not return a complete response matching the contract."""


class LLMClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    async def complete_json(
        self, *, model: str, system_prompt: str, content: str | list[dict], schema: type[Output]
    ) -> Output:
        prompt = (
            system_prompt + "\nReturn only a JSON object matching this schema. "
            "No Markdown fences or additional prose.\n" + json.dumps(schema.model_json_schema())
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "max_tokens": self.config.llm_max_output_tokens,
            "stream": False,
        }
        if self.config.llm_json_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(
                base_url=self.config.litellm_base_url.rstrip("/") + "/",
                headers={"Authorization": f"Bearer {self.config.litellm_api_key}"},
                timeout=self.config.llm_timeout_seconds,
            ) as client:
                response = await client.post("chat/completions", json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 429 or code >= 500:
                raise LLMUnavailableError(f"LLM proxy returned HTTP {code}") from exc
            raise LLMOutputError(f"LLM proxy rejected the request (HTTP {code})") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError("LLM proxy could not be reached") from exc
        try:
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                raise LLMOutputError("LLM response was incomplete or refused")
            text = choice["message"]["content"]
            if not isinstance(text, str):
                raise LLMOutputError("LLM response did not contain JSON text")
            text = text.strip()
            if text.startswith("```") and text.endswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return schema.model_validate_json(text)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            # Never include the model response or validation input in the exception.
            raise LLMOutputError("LLM output does not match the required JSON schema") from exc
