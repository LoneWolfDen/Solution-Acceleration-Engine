# Unified LLM Client Usage Guide

This document shows how to use the new unified LLM client factory in backend processing routers.

## Overview

The new unified LLM client factory provides a platform-agnostic way to make LLM calls with proper timeout handling, base URL support, and API key management.

## Key Benefits

1. **Platform Agnostic**: Works with NVIDIA, Groq, OpenAI, and other providers
2. **Centralized Configuration**: All LLM settings managed in one place
3. **Timeout Control**: Explicit timeout handling to prevent long-query timeouts
4. **Base URL Support**: Proper handling for NVIDIA NIM and other custom endpoints

## Example: Updating a Router to Use Unified Client

Here's how to update a backend router to use the new unified client:

### Before (Legacy approach):
```python
# In routers/reviews.py or similar
from contexta.llm.provider import call_llm, LLMConfig

# Legacy approach - hardcoded provider resolution
async def some_llm_function():
    # ... existing code to get config from DB ...
    config = LLMConfig(
        model="groq/llama3-8b-8192",
        api_key=api_key,
        base_url=None
    )
    
    response = await call_llm(
        config=config,
        system="system prompt",
        user="user prompt",
        max_tokens=4096
    )
    return response
```

### After (Unified approach):
```python
# In routers/reviews.py or similar
from contexta.llm.client_factory import get_llm_client
from contexta.config import load_config

async def some_llm_function():
    # Load unified configuration
    config = load_config()
    
    # Get unified LLM client
    client = await get_llm_client(config)
    
    # Use the client with proper timeout handling
    response = await client(
        system="system prompt",
        user="user prompt",
        max_tokens=4096
    )
    return response
```

## Complete Example Implementation

Here's a complete example showing how to integrate the unified client in a router:

```python
# In your router file (e.g., contexta/api/routers/reviews.py)

from contexta.config import load_config
from contexta.llm.client_factory import get_llm_client
from contexta.llm.provider import LLMCallError

@router.post("/reviews", response_model=schemas.CreateReviewResponse, status_code=202)
async def create_review(
    body: schemas.CreateReviewRequest,
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.CreateReviewResponse:
    # ... existing code ...
    
    # Get unified configuration
    app_config = load_config()
    
    # Get unified LLM client
    llm_client = await get_llm_client(app_config)
    
    # Use the client for LLM calls throughout your pipeline
    # Example usage:
    try:
        response = await llm_client(
            system="You are a helpful assistant...",
            user="Please analyze this content...",
            max_tokens=4096
        )
        # Process response...
    except TimeoutError:
        # Handle timeout specifically
        logger.error("LLM call timed out")
        raise HTTPException(status_code=504, detail="LLM call timed out")
    except LLMCallError as e:
        # Handle other LLM errors
        logger.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=500, detail="LLM processing failed")
    
    # ... rest of existing code ...
```

## Configuration Variables

The unified client supports these environment variables:

- `LLM_PROVIDER` - LLM provider name (e.g., "nvidia", "groq", "openai")
- `LLM_MODEL_NAME` - LLM model name (e.g., "meta/llama-3.1-70b-instruct", "llama3-70b-8192")
- `LLM_API_KEY` - API key (automatically mapped based on provider)
- `LLM_BASE_URL` - Base URL (crucial for NVIDIA NIM)
- `LLM_TIMEOUT` - Timeout in seconds (default 120)

## Migration Steps

1. Import the new client factory: `from contexta.llm.client_factory import get_llm_client`
2. Load configuration: `config = load_config()`
3. Get client: `client = await get_llm_client(config)`
4. Replace `call_llm()` calls with `await client()`
5. Handle timeout errors appropriately

## Backward Compatibility

The unified client maintains full backward compatibility with existing code patterns. The `get_default_llm_config()` function can be used when you need just the configuration object without the client wrapper.