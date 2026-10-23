"""Structured provider failover; callers validate values and own all state changes."""
import json
from typing import TypeVar
import httpx
from pydantic import BaseModel
from app.core.config import settings

T = TypeVar("T", bound=BaseModel)


def strict_schema(schema: dict) -> dict:
    result = dict(schema)
    result.pop("default", None)
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    for key, value in list(result.items()):
        if isinstance(value, dict):
            result[key] = {k: strict_schema(v) if isinstance(v, dict) else v for k, v in value.items()} if key in {"properties", "$defs"} else strict_schema(value)
        elif isinstance(value, list):
            result[key] = [strict_schema(item) if isinstance(item, dict) else item for item in value]
    return result


async def structured(contract: type[T], instruction: str, prompt: str) -> tuple[T, str]:
    if not settings.BUYER_AI_ENABLED:
        raise ValueError("AI disabled")
    choices = [settings.BUYER_AI_PRIMARY, "openai" if settings.BUYER_AI_PRIMARY == "gemini" else "gemini"]
    for provider in choices:
        if provider == "gemini" and not settings.GEMINI_API_KEY:
            continue
        if provider == "openai" and not settings.OPENAI_API_KEY.get_secret_value():
            continue
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                if provider == "gemini":
                    response = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.BUYER_GEMINI_MODEL}:generateContent",
                        headers={"x-goog-api-key": settings.GEMINI_API_KEY}, json={
                            "systemInstruction": {"parts": [{"text": instruction}]},
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": contract.model_json_schema(), "maxOutputTokens": 1024}})
                    response.raise_for_status()
                    raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    response = await client.post("https://api.openai.com/v1/responses",
                        headers={"Authorization": "Bearer " + settings.OPENAI_API_KEY.get_secret_value()},
                        json={"model": settings.BUYER_OPENAI_MODEL, "instructions": instruction,
                            "input": prompt, "store": False, "max_output_tokens": 1024,
                            "text": {"format": {"type": "json_schema", "name": contract.__name__,
                                "strict": True, "schema": strict_schema(contract.model_json_schema())}}})
                    response.raise_for_status()
                    raw = "".join(part["text"] for item in response.json()["output"]
                        for part in item.get("content", []) if part.get("type") == "output_text")
                return contract.model_validate_json(raw), provider
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            continue
    raise ValueError("No provider returned a valid structured result")
