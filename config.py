#!/usr/bin/env python3
import os
from typing import Optional


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        # Safe to ignore if python-dotenv is not installed
        pass


def env_str(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


def require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


def openai_model_default() -> str:
    return env_str("OPENAI_MODEL", "o3") or "o3"


def get_openai_client():
    """
    Returns an OpenAI client using the API key from env.
    Respects optional OPENAI_BASE_URL for self-hosted gateways.
    """
    load_dotenv_if_available()
    from openai import OpenAI  # type: ignore

    api_key = require_env("OPENAI_API_KEY")
    base_url = env_str("OPENAI_BASE_URL")

    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def get_vision_client():
    """
    Returns a Google Cloud Vision ImageAnnotatorClient configured with an API key
    provided in GOOGLE_VISION_API_KEY. This uses API key via client_options.
    """
    load_dotenv_if_available()
    from google.cloud import vision  # type: ignore

    api_key = require_env("GOOGLE_VISION_API_KEY")
    return vision.ImageAnnotatorClient(client_options={"api_key": api_key})
