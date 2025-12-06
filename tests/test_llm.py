"""Tests for LLM client."""

from unittest.mock import MagicMock, patch

import pytest

from ringtwice.config import LLMConfig
from ringtwice.llm import LLMClient, LLMResponse


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create test LLM config."""
    return LLMConfig(
        endpoint="https://api.example.com/v1",
        api_key="test-key",
        model="test-model",
        max_context=4096,
    )


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create(self) -> None:
        """Test creating response."""
        response = LLMResponse(
            content="Hello",
            model="test-model",
            usage_prompt_tokens=10,
            usage_completion_tokens=5,
        )
        assert response.content == "Hello"
        assert response.model == "test-model"


class TestLLMClient:
    """Tests for LLMClient."""

    def test_count_tokens_returns_positive_int(self, llm_config: LLMConfig) -> None:
        """Test token counting works."""
        client = LLMClient(llm_config)
        result = client.count_tokens("Hello world")
        assert isinstance(result, int)
        assert result > 0

    def test_count_tokens_empty_string(self, llm_config: LLMConfig) -> None:
        """Test token counting for empty string."""
        client = LLMClient(llm_config)
        result = client.count_tokens("")
        assert result == 0

    def test_split_for_context_short_text(self, llm_config: LLMConfig) -> None:
        """Test short text returns single chunk."""
        client = LLMClient(llm_config)
        result = client.split_for_context("Short text")
        assert len(result) == 1
        assert result[0] == "Short text"

    def test_split_for_context_long_text(self, llm_config: LLMConfig) -> None:
        """Test long text is split into multiple chunks."""
        # Create small context to force splitting
        config = LLMConfig(
            endpoint="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_context=1200,  # Small enough to force splitting of long text
        )
        client = LLMClient(config)

        # Create text longer than context (each "word " is ~1-2 tokens)
        long_text = "word " * 500
        result = client.split_for_context(long_text)

        # Should have multiple chunks
        assert len(result) > 1

    def test_complete_returns_response(self, llm_config: LLMConfig) -> None:
        """Test complete returns LLMResponse."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response text"
        mock_response.model = "test-model"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        with patch.object(LLMClient, "__init__", lambda self, config: None):
            client = LLMClient.__new__(LLMClient)
            client._config = llm_config
            client._client = MagicMock()
            client._client.chat.completions.create.return_value = mock_response
            client._tokenizer = MagicMock()
            client._splitter = MagicMock()

            result = client.complete("System prompt", "User content")

            assert isinstance(result, LLMResponse)
            assert result.content == "Response text"
            assert result.model == "test-model"
            assert result.usage_prompt_tokens == 10
            assert result.usage_completion_tokens == 5

    def test_complete_handles_none_content(self, llm_config: LLMConfig) -> None:
        """Test complete handles None content from API."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.model = "test-model"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 0

        with patch.object(LLMClient, "__init__", lambda self, config: None):
            client = LLMClient.__new__(LLMClient)
            client._config = llm_config
            client._client = MagicMock()
            client._client.chat.completions.create.return_value = mock_response
            client._tokenizer = MagicMock()
            client._splitter = MagicMock()

            result = client.complete("System prompt", "User content")
            assert result.content == ""

    def test_process_batch_yields_responses(self, llm_config: LLMConfig) -> None:
        """Test process_batch yields responses for each content."""
        with patch.object(LLMClient, "__init__", lambda self, config: None):
            client = LLMClient.__new__(LLMClient)
            client._config = llm_config
            client._splitter = MagicMock()
            client._splitter.chunks.side_effect = lambda x: [x]  # No splitting

            # Mock complete to return predictable responses
            mock_responses = [
                LLMResponse("Response 1", "model", 10, 5),
                LLMResponse("Response 2", "model", 10, 5),
            ]
            client.complete = MagicMock(side_effect=mock_responses)

            results = list(client.process_batch("prompt", ["content1", "content2"]))

            assert len(results) == 2
            assert results[0].content == "Response 1"
            assert results[1].content == "Response 2"

    def test_uses_fallback_tokenizer(self) -> None:
        """Test fallback tokenizer for unknown models."""
        config = LLMConfig(
            endpoint="https://api.example.com/v1",
            api_key="test-key",
            model="unknown-model-xyz",  # Not a known OpenAI model
            max_context=4096,
        )
        # Should not raise, uses cl100k_base fallback
        client = LLMClient(config)
        assert client.count_tokens("Hello") > 0
