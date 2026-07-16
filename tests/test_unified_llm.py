"""
Test for the unified LLM client factory.
"""
import pytest
from contexta.config import ContextaConfig
from contexta.llm.client_factory import get_default_llm_config


def test_get_default_llm_config():
    """Test that the default LLM config works with various configurations."""
    
    # Test with basic configuration
    config = ContextaConfig(
        llm_backend="groq/llama3-8b-8192",
        llm_api_key="test-key",
        llm_base_url="https://api.groq.com/openai/v1"
    )
    
    llm_config = get_default_llm_config(config)
    
    assert llm_config.model == "groq/llama3-8b-8192"
    assert llm_config.api_key == "test-key"
    assert llm_config.base_url == "https://api.groq.com/openai/v1"
    
    # Test with provider and model name
    config2 = ContextaConfig(
        llm_backend="groq/llama3-8b-8192",
        llm_provider="nvidia",
        llm_model_name="meta/llama-3.1-70b-instruct",
        llm_api_key="test-key-2"
    )
    
    llm_config2 = get_default_llm_config(config2)
    
    # Should use the provider/model name when both are provided
    assert llm_config2.model == "nvidia/meta/llama-3.1-70b-instruct"
    assert llm_config2.api_key == "test-key-2"
    assert llm_config2.base_url is None


if __name__ == "__main__":
    pytest.main([__file__])