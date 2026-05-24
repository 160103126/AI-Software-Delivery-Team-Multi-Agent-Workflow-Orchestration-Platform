from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()
load_dotenv(".ENV")


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )

    logger = logging.getLogger(__name__)

    # Log LangSmith tracing status on startup
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    api_key_set = bool(os.getenv("LANGCHAIN_API_KEY", "").strip())
    project = os.getenv("LANGCHAIN_PROJECT", "default")

    if tracing_enabled and api_key_set:
        logger.info(
            "LangSmith tracing ENABLED: project=%s endpoint=%s",
            project,
            os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"),
        )
    elif tracing_enabled and not api_key_set:
        logger.warning(
            "LANGCHAIN_TRACING_V2 is true but LANGCHAIN_API_KEY is not set — tracing will fail. "
            "Set your API key or disable tracing."
        )
    else:
        logger.info("LangSmith tracing DISABLED (set LANGCHAIN_TRACING_V2=true to enable)")
