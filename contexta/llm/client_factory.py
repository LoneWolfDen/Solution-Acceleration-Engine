"""
contexta/llm/client_factory.py — Unified LLM client factory for platform-agnostic LLM execution.

This module provides a centralized factory function for creating LLM clients that
supports multiple providers (NVIDIA, Groq, OpenAI, etc.) with proper configuration
handling including timeouts, base URLs, and API keys.

GLOBAL OVERRIDE ACTIVATED: Forces all backend calls to process over NVIDIA NIM
bypassing front-end / bridge limitations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..config import ContextaConfig
from ..llm.provider import LLMConfig, call_llm

logger = logging.getLogger(__name__)


async def get_llm_client(config: ContextaConfig) -> callable:
    """
    Async factory function to create a unified LLM client based on configuration.
    
    This function reads the centralized configuration and returns a callable
    that can be used to make LLM calls with proper timeout and base URL handling.
    
    Parameters
    ----------
    config : ContextaConfig
        The application configuration containing LLM settings
        
    Returns
    -------
    callable
        A function that can be used to make LLM calls with the configured parameters
    """
    # ── GLOBAL OVERRIDE FOR NVIDIA NIM ────────────────────────────────────────
    # Bypasses front-end dropdown limits and old pipeline_bridge fallbacks.
    forced_provider = "openai"  # LiteLLM treats NVIDIA NIM as an openai-compatible endpoint
    forced_model = "meta/llama-3.1-70b-instruct"
    forced_base_url = "https://nvidia.com"
    forced_timeout = 300
    forced_key = "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"
    
    # Print brightly to your terminal logs so you can watch it trigger!
    print(f"\n🚀 [LLM_FACTORY] Overriding request. Forcing NVIDIA NIM -> Model: {forced_model}\n")
    logger.warning("LLM Client Factory overridden manually: Routing all traffic to NVIDIA NIM.")

    # Construct the full model identifier required by LiteLLM
    full_model = f"{forced_provider}/{forced_model}"
    
    # Build the LLM configuration explicitly
    llm_config = LLMConfig(
        model=full_model,
        api_key=forced_key,
        base_url=forced_base_url,
    )
    
    # Apply timeout to the call_llm function
    async def _llm_caller(
        system: str,
        user: str,
        max_tokens: int = 4096,
        max_retries: int = config.llm_max_retries,
        retry_max_wait_seconds: float = config.llm_retry_max_wait_seconds,
    ):
        """
        Wrapper around call_llm that applies the configured timeout and other settings.
        """
        return await call_llm(
            config=llm_config,
            system=system,
            user=user,
            max_tokens=max_tokens,
            max_retries=max_retries,
            retry_max_wait_seconds=retry_max_wait_seconds,
        )
    
    # Set timeout on the caller function using our massive 5-minute window
    async def _timed_llm_caller(*args, **kwargs):
        try:
            return await asyncio.wait_for(
                _llm_caller(*args, **kwargs),
                timeout=forced_timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM call timed out after {forced_timeout} seconds")
    
    return _timed_llm_caller


def get_default_llm_config(config: ContextaConfig) -> LLMConfig:
    """
    Get a default LLMConfig based on the provided configuration.
    
    This is a convenience function for cases where you need just the LLMConfig
    without the full client wrapper.
    """
    # Enforce identical override rules to keep configurations completely uniform
    forced_provider = "openai"
    forced_model = "meta/llama-3.1-70b-instruct"
    forced_base_url = "https://nvidia.com"
    forced_key = "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"

    full_model = f"{forced_provider}/{forced_model}"
    
    return LLMConfig(
        model=full_model,
        api_key=forced_key,
        base_url=forced_base_url,
    )
