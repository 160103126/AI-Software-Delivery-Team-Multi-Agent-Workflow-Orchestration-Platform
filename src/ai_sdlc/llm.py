from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError

load_dotenv()
load_dotenv(".ENV")


def llm_enabled() -> bool:
    if os.getenv("AI_SDLC_USE_LLM", "true").lower() in {"0", "false", "no"}:
        return False
    return bool(os.getenv("GOOGLE_API_KEY"))


@lru_cache
def get_gemini_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.2")),
        response_mime_type="application/json",
    )


def invoke_json_model(system_prompt: str, user_prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
    if not llm_enabled():
        raise RuntimeError("LLM is disabled or GOOGLE_API_KEY is not configured.")

    response = get_gemini_model().invoke(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )
    content = response.content
    if not isinstance(content, str):
        content = json.dumps(content)

    try:
        parsed = json.loads(content)
        return schema.model_validate(parsed).model_dump()
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Gemini returned invalid structured output: {exc}") from exc
