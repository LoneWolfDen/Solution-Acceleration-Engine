"""
contexta/llm/client_factory.py — Unified LLM client factory for platform-agnostic LLM execution.

This module provides a centralized factory function for creating LLM clients that
supports multiple providers (NVIDIA, Groq, OpenAI, etc.) with proper configuration
handling including timeouts, base URLs, and API keys.
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
    
    # Determine the provider and model name
    provider = config.llm_provider or "unknown"
    model_name = config.llm_model_name
    
    # If we have a provider but no model name, try to derive it from the backend
    if provider != "unknown" and not model_name:
        if "/" in config.llm_backend:
            model_name = config.llm_backend.split("/", 1)[1]
        else:
            model_name = config.llm_backend
    
    # Construct the full model identifier
    if model_name and provider != "unknown":
        full_model = f"{provider}/{model_name}"
    elif model_name:
        full_model = model_name
    else:
        # Fall back to the existing backend if no provider/model info available
        full_model = config.llm_backend
    
    # Build the LLM configuration
    llm_config = LLMConfig(
        model=full_model,
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
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
        
        Parameters
        ----------
        system : str
            System role message
        user : str
            User role message
        max_tokens : int
            Maximum tokens to generate
        max_retries : int
            Maximum retry attempts
        retry_max_wait_seconds : float
            Maximum wait time for retries
            
        Returns
        -------
        LLMResponse
            The response from the LLM call
        """
        return await call_llm(
            config=llm_config,
            system=system,
            user=user,
            max_tokens=max_tokens,
            max_retries=max_retries,
            retry_max_wait_seconds=retry_max_wait_seconds,
        )
    
    # Set timeout on the caller function
    async def _timed_llm_caller(*args, **kwargs):
        try:
            # Apply the timeout to the LLM call
            return await asyncio.wait_for(
                _llm_caller(*args, **kwargs),
                timeout=config.llm_timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM call timed out after {config.llm_timeout} seconds")
    
    return _timed_llm_caller


def get_default_llm_config(config: ContextaConfig) -> LLMConfig:
    """
    Get a default LLMConfig based on the provided configuration.
    
    This is a convenience function for cases where you need just the LLMConfig
    without the full client wrapper.
    
    Parameters
    ----------
    config : ContextaConfig
        The application configuration
        
    Returns
    -------
    LLMConfig
        The LLM configuration object
    """
    # Determine the provider and model name
    provider = config.llm_provider or "unknown"
    model_name = config.llm_model_name
    
    # If we have a provider but no model name, try to derive it from the backend
    if provider != "unknown" and not model_name:
        if "/" in config.llm_backend:
            model_name = config.llm_backend.split("/", 1)[1]
        else:
            model_name = config.llm_backend
    
    # Construct the full model identifier
    if model_name and provider != "unknown":
        full_model = f"{provider}/{model_name}"
    elif model_name:
        full_model = model_name
    else:
        # Fall back to the existing backend if no provider/model info available
        full_model = config.llm_backend
    
    return LLMConfig(
        model=full_model,
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
    )