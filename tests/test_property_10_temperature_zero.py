"""Property 10 — Temperature-Zero LLM Call Invariant.

For every call to ``call_llm()`` — regardless of the ``LLMConfig``, system
prompt, user message, or ``max_tokens`` value — the underlying
``litellm.acompletion`` mock must receive:
  - ``temperature=0.0``  (exactly, not 0 or 0.00001)
  - ``response_format={"type": "json_object"}``

No caller-supplied argument may override either of these values.

This module covers:
1. Unit tests asserting the exact kwarg values captured by the mock.
2. Hypothesis tests generating arbitrary configs, prompts, and token limits
   and asserting the invariant holds for all combinations.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contexta.llm.provider import LLMConfig, LLMResponse, call_llm, _TEMPERATURE, _RESPONSE_FORMAT


# ── Mock factory ──────────────────────────────────────────────────────────────


def _make_acompletion_mock(content: str = '{"ok": true}') -> AsyncMock:
    """Return an ``AsyncMock`` that mimics the minimal litellm response shape."""
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]

    return AsyncMock(return_value=response)


# ── Module-level constant tests ───────────────────────────────────────────────


class TestTemperatureConstants:
    """The module-level constants must never be changed."""

    def test_temperature_constant_value(self):
        assert _TEMPERATURE == 0.0
        assert type(_TEMPERATURE) is float

    def test_response_format_constant_value(self):
        assert _RESPONSE_FORMAT == {"type": "json_object"}
        assert isinstance(_RESPONSE_FORMAT, dict)
        assert len(_RESPONSE_FORMAT) == 1


# ── call_llm unit tests ───────────────────────────────────────────────────────


class TestCallLLMTemperatureZero:
    """Direct unit tests for the kwarg invariant."""

    @pytest.mark.asyncio
    async def test_temperature_is_zero_point_zero(self, llm_config: LLMConfig):
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="sys", user="usr")

        _, kwargs = mock.call_args
        assert kwargs["temperature"] == 0.0
        assert type(kwargs["temperature"]) is float

    @pytest.mark.asyncio
    async def test_response_format_is_json_object(self, llm_config: LLMConfig):
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="sys", user="usr")

        _, kwargs = mock.call_args
        assert kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_both_constraints_in_single_call(self, llm_config: LLMConfig):
        """Single assertion covering both constraints together."""
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="review system", user="user input")

        _, kwargs = mock.call_args
        assert kwargs["temperature"] == 0.0
        assert kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_model_name_passed_through(self, llm_config: LLMConfig):
        """Model name from config reaches litellm unchanged."""
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="s", user="u")

        _, kwargs = mock.call_args
        assert kwargs["model"] == llm_config.model

    @pytest.mark.asyncio
    async def test_api_key_passed_when_set(self, llm_config_with_key: LLMConfig):
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config_with_key, system="s", user="u")

        _, kwargs = mock.call_args
        assert kwargs["api_key"] == llm_config_with_key.api_key
        # Temperature and format still enforced
        assert kwargs["temperature"] == 0.0
        assert kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_base_url_passed_when_set(self, llm_config_with_key: LLMConfig):
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config_with_key, system="s", user="u")

        _, kwargs = mock.call_args
        assert kwargs["base_url"] == llm_config_with_key.base_url

    @pytest.mark.asyncio
    async def test_api_key_absent_when_none(self, llm_config: LLMConfig):
        """``api_key`` kwarg must not appear when config.api_key is None."""
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="s", user="u")

        _, kwargs = mock.call_args
        assert "api_key" not in kwargs

    @pytest.mark.asyncio
    async def test_base_url_absent_when_none(self, llm_config: LLMConfig):
        """``base_url`` kwarg must not appear when config.base_url is None."""
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="s", user="u")

        _, kwargs = mock.call_args
        assert "base_url" not in kwargs

    @pytest.mark.asyncio
    async def test_messages_structure(self, llm_config: LLMConfig):
        """Messages list has exactly system + user roles in order."""
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="my system", user="my user")

        _, kwargs = mock.call_args
        messages = kwargs["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "my system"}
        assert messages[1] == {"role": "user", "content": "my user"}

    @pytest.mark.asyncio
    async def test_custom_max_tokens_passed(self, llm_config: LLMConfig):
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            await call_llm(llm_config, system="s", user="u", max_tokens=512)

        _, kwargs = mock.call_args
        assert kwargs["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_return_value_shape(self, llm_config: LLMConfig):
        """``call_llm()`` returns an ``LLMResponse`` with the mocked content."""
        mock = _make_acompletion_mock('{"result": "ok"}')
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            result = await call_llm(llm_config, system="s", user="u")

        assert isinstance(result, LLMResponse)
        assert result.content == '{"result": "ok"}'
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_multiple_consecutive_calls_all_zero_temp(self, llm_config: LLMConfig):
        """Every call in a sequence enforces temperature=0.0."""
        mock = _make_acompletion_mock()
        with patch("contexta.llm.provider.litellm.acompletion", mock):
            for _ in range(5):
                await call_llm(llm_config, system="s", user="u")

        assert mock.call_count == 5
        for call in mock.call_args_list:
            _, kwargs = call
            assert kwargs["temperature"] == 0.0
            assert kwargs["response_format"] == {"type": "json_object"}


# ── Hypothesis property test ──────────────────────────────────────────────────


_model_strategy = st.builds(
    LLMConfig,
    model=st.from_regex(r"[a-z]+/[a-z0-9\-]+", fullmatch=True),
    api_key=st.one_of(st.none(), st.text(min_size=1, max_size=64)),
    base_url=st.one_of(st.none(), st.just("https://api.example.com")),
)


@given(
    config=_model_strategy,
    system=st.text(max_size=500),
    user=st.text(max_size=500),
    max_tokens=st.integers(min_value=1, max_value=8192),
)
@settings(max_examples=300)
def test_property_10_temperature_zero_invariant(
    config: LLMConfig,
    system: str,
    user: str,
    max_tokens: int,
) -> None:
    """Property 10: temperature==0.0 and response_format==json_object for ALL inputs.

    Hypothesis generates arbitrary LLMConfig, prompts, and token limits.
    The mock captures every kwarg set on litellm.acompletion and the
    assertion is evaluated inside asyncio.run().
    """
    captured: dict[str, Any] = {}

    async def _run() -> None:
        mock = _make_acompletion_mock()

        async def _capture(**kwargs: Any):
            captured.update(kwargs)
            return mock.return_value

        with patch("contexta.llm.provider.litellm.acompletion", side_effect=_capture):
            await call_llm(config, system=system, user=user, max_tokens=max_tokens)

        assert captured.get("temperature") == 0.0, (
            f"temperature was {captured.get('temperature')!r}, expected 0.0"
        )
        assert captured.get("response_format") == {"type": "json_object"}, (
            f"response_format was {captured.get('response_format')!r}"
        )

    asyncio.run(_run())
