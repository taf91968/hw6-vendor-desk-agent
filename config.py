"""Shared model setup for the Homework 6 vendor desk agent.

All AI calls go through Portkey with PORTKEY_API_KEY, using gpt-6-luna only.
The key is read from the environment or a .env file (this folder or any parent).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx2  # the HTTP client the openai SDK uses
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
for folder in [HERE, *HERE.parents]:
    if (folder / ".env").exists():
        load_dotenv(folder / ".env", override=False)

ALLOWED_MODEL = "gpt-6-luna"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", ALLOWED_MODEL)
if OPENAI_MODEL != ALLOWED_MODEL:
    raise RuntimeError(f"Homework 6 uses {ALLOWED_MODEL} only (OPENAI_MODEL is set to {OPENAI_MODEL!r}).")

PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "90"))  # never hang forever on one request

# Raw usage block of every model call, exactly as the API sent it back (filled by the HTTP hook below).
API_CALLS: list[dict] = []


async def _capture_usage(response: httpx2.Response) -> None:
    if response.request.method != "POST" or not response.request.url.path.endswith("/responses"):
        return
    await response.aread()
    try:
        body = response.json()
    except ValueError:
        return
    API_CALLS.append({
        "status_code": response.status_code,
        "response_id": body.get("id"),
        "model": body.get("model"),
        "usage": body.get("usage"),
        # Portkey's own response cache (separate from OpenAI prompt caching): HIT / MISS / DISABLED / REFRESH
        "portkey_cache_status": response.headers.get("x-portkey-cache-status"),
    })


def build_model(extra_headers: dict[str, str] | None = None) -> OpenAIResponsesModel:
    """gpt-6-luna via Portkey. Uses the Responses API, which this model needs for function tools."""
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Set it in your environment or a .env file.")
    client = AsyncOpenAI(
        api_key=key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": "openai", **(extra_headers or {})},
        timeout=TIMEOUT_SECONDS,
        max_retries=2,
        http_client=httpx2.AsyncClient(timeout=TIMEOUT_SECONDS, event_hooks={"response": [_capture_usage]}),
    )
    return OpenAIResponsesModel(OPENAI_MODEL, provider=OpenAIProvider(openai_client=client))
