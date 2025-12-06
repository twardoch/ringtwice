"""LLM client for OpenAI-compatible endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import tiktoken
from openai import OpenAI
from semantic_text_splitter import TextSplitter
from tenacity import retry, stop_after_attempt, wait_exponential

from ringtwice.config import LLMConfig


@dataclass
class LLMResponse:
    """Response from LLM."""

    content: str
    model: str
    usage_prompt_tokens: int
    usage_completion_tokens: int


class LLMClient:
    """Client for OpenAI-compatible LLM endpoints."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = OpenAI(
            base_url=config.endpoint,
            api_key=config.api_key,
        )
        # Use tiktoken for token counting (approximate for non-OpenAI models)
        try:
            self._tokenizer = tiktoken.encoding_for_model(config.model)
        except KeyError:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")

        # Reserve tokens for prompt and response
        max_content_tokens = max(config.max_context - 1000, 100)
        self._splitter = TextSplitter(max_content_tokens)

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self._tokenizer.encode(text))

    def split_for_context(self, text: str) -> list[str]:
        """Split text to fit within context window."""
        return self._splitter.chunks(text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def complete(self, prompt: str, content: str) -> LLMResponse:
        """Send content to LLM with prompt."""
        response = self._client.chat.completions.create(
            model=self._config.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
        )
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            usage_prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            usage_completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    def process_batch(self, prompt: str, contents: list[str]) -> Iterator[LLMResponse]:
        """Process multiple content pieces, respecting context limits."""
        for content in contents:
            chunks = self.split_for_context(content)
            for chunk in chunks:
                yield self.complete(prompt, chunk)
