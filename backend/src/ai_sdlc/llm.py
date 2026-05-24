from __future__ import annotations

import hashlib
import json
import logging
import os
from functools import lru_cache
from typing import Any, List

import redis
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, ValidationError

load_dotenv()
load_dotenv(".ENV")

logger = logging.getLogger(__name__)

# Redis client for LLM response caching
_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis | None:
    """Get or initialize Redis client for caching."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.debug("REDIS_URL not set, caching disabled")
        return None

    try:
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        logger.info("Connected to Redis for LLM caching")
        return _redis_client
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}, caching disabled")
        return None


def _cache_key(system_prompt: str, user_prompt: str, schema_name: str) -> str:
    """Generate cache key for LLM request."""
    key_data = f"{system_prompt}:{user_prompt}:{schema_name}"
    return f"llm_cache:{hashlib.sha256(key_data.encode()).hexdigest()}"


def _env_value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _provider() -> str:
    return _env_value("AI_SDLC_LLM_PROVIDER", "vertex").lower()


def llm_enabled() -> bool:
    if os.getenv("AI_SDLC_USE_LLM", "true").lower() in {"0", "false", "no"}:
        logger.debug("LLM disabled by AI_SDLC_USE_LLM")
        return False
    if _provider() == "vertex":
        enabled = bool(_env_value("GOOGLE_CLOUD_PROJECT"))
        logger.debug("Vertex LLM enabled check: project_set=%s", enabled)
        return enabled
    enabled = bool(_env_value("GOOGLE_API_KEY"))
    logger.debug("Google API LLM enabled check: api_key_set=%s", enabled)
    return enabled


@lru_cache
def get_gemini_model() -> ChatGoogleGenerativeAI:
    model = _env_value("GEMINI_MODEL", "gemini-2.5-flash-lite")
    temperature = float(_env_value("GEMINI_TEMPERATURE", "0.2"))

    if _provider() == "vertex":
        logger.info(
            "Initializing Gemini via Vertex AI: model=%s project=%s location=%s temperature=%s",
            model,
            _env_value("GOOGLE_CLOUD_PROJECT"),
            _env_value("GOOGLE_CLOUD_LOCATION", "global"),
            temperature,
        )
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            response_mime_type="application/json",
            vertexai=True,
            project=_env_value("GOOGLE_CLOUD_PROJECT"),
            location=_env_value("GOOGLE_CLOUD_LOCATION", "global"),
        )

    logger.info(
        "Initializing Gemini via Google API: model=%s api_key_set=%s temperature=%s",
        model,
        bool(_env_value("GOOGLE_API_KEY")),
        temperature,
    )
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        response_mime_type="application/json",
    )


def invoke_json_model(system_prompt: str, user_prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
    if not llm_enabled():
        raise RuntimeError(
            "LLM is disabled or provider credentials are not configured. "
            "For Vertex mode, set GOOGLE_CLOUD_PROJECT and authenticate with ADC."
        )

    # Check Redis cache first
    redis_client = _get_redis_client()
    cache_key = _cache_key(system_prompt, user_prompt, schema.__name__)

    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                result = json.loads(cached)
                logger.info(f"Cache hit for schema={schema.__name__}")
                return result
        except Exception as e:
            logger.warning(f"Redis cache lookup failed: {e}")

    logger.info("Calling Gemini for schema=%s provider=%s", schema.__name__, _provider())
    try:
        response = get_gemini_model().invoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
    except Exception:
        logger.exception("Gemini call failed for schema=%s", schema.__name__)
        raise

    content = response.content
    if not isinstance(content, str):
        content = json.dumps(content)

    try:
        parsed = json.loads(content)
        validated = schema.model_validate(parsed).model_dump()
        logger.info("Gemini returned valid structured output for schema=%s", schema.__name__)

        # Cache the result (24 hour TTL)
        if redis_client:
            try:
                redis_client.setex(cache_key, 86400, json.dumps(validated))
                logger.debug(f"Cached result for schema={schema.__name__}")
            except Exception as e:
                logger.warning(f"Failed to cache result: {e}")

        return validated
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Gemini returned invalid structured output for schema=%s: %s", schema.__name__, exc)
        raise ValueError(f"Gemini returned invalid structured output: {exc}") from exc


def invoke_agent_with_tools(system_prompt: str, user_prompt: str, tools: List[Any]) -> str:
    """Run a ReAct loop using the provided tools and prompts."""
    if not llm_enabled():
        raise RuntimeError(
            "LLM is disabled or provider credentials are not configured. "
            "For Vertex mode, set GOOGLE_CLOUD_PROJECT and authenticate with ADC."
        )

    logger.info(f"Creating ReAct agent with {len(tools)} tools using provider={_provider()}")
    llm = get_gemini_model()
    
    try:
        agent = create_react_agent(llm, tools=tools, prompt=system_prompt)
        # Use invoke. The state has a 'messages' key.
        response = agent.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            {"recursion_limit": 30}  # Increased limit to allow more tool iterations for debugging
        )
        
        # The final answer is the content of the last message
        content = response["messages"][-1].content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    texts.append(item["text"])
            return "\n".join(texts)
        return str(content)
    except Exception as e:
        logger.exception("ReAct agent execution failed")
        raise ValueError(f"Agent execution failed: {e}") from e
