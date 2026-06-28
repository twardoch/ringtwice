"""Connects to LLMs matching the OpenAI API spec (Ollama, vLLM, OpenAI)."""

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
    """The raw text and token usage metrics returned by the LLM."""

    content: str
    model: str
    usage_prompt_tokens: int
    usage_completion_tokens: int


class LLMClient:
    """Handles prompt chunking and HTTP requests to OpenAI-compatible APIs."""

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
        """Measure precise token count using tiktoken encoding."""
        return len(self._tokenizer.encode(text))

    def split_for_context(self, text: str) -> list[str]:
        """Chop large text blocks into pieces that safely fit the LLM context window."""
        return self._splitter.chunks(text)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def complete(self, prompt: str, content: str) -> LLMResponse:
        """Send *content* to the LLM with *prompt* as the system instruction.

        The chat-completions API is used even for models that don't distinguish
        system/user roles; most OpenAI-compatible servers accept this framing.

        Args:
            prompt: System-level instruction (what to extract / how to respond).
            content: Email body text already cleaned by EmailProcessor.

        Returns:
            LLMResponse with the model's text reply and token usage counters.
        """
        raw = self._client.chat.completions.create(
            model=self._config.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
        )
        # Extract the reply text, defaulting to empty string if the model
        # returned a refusal or a purely tool-call response.
        reply_text: str = raw.choices[0].message.content or ""
        prompt_tokens: int = raw.usage.prompt_tokens if raw.usage else 0
        completion_tokens: int = raw.usage.completion_tokens if raw.usage else 0
        return LLMResponse(
            content=reply_text,
            model=raw.model,
            usage_prompt_tokens=prompt_tokens,
            usage_completion_tokens=completion_tokens,
        )

    def process_batch(self, prompt: str, contents: list[str]) -> Iterator[LLMResponse]:
        """Yield one LLMResponse per context-window chunk across all *contents*.

        Each content string is split by split_for_context() before being sent,
        so a very long email body never exceeds the configured token ceiling.

        Args:
            prompt: System instruction passed to every LLM call.
            contents: Pre-cleaned email body strings to process in sequence.

        Yields:
            LLMResponse for each chunk dispatched to the model.
        """
        for content in contents:
            chunks = self.split_for_context(content)
            for chunk in chunks:
                yield self.complete(prompt, chunk)
