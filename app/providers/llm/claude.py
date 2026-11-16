from contextlib import AbstractContextManager, nullcontext
from typing import Any

from anthropic import AsyncAnthropic, AsyncAnthropicBedrockMantle, BetaFallbackState

from app.providers.llm.base import LLMResponse, Message


class ClaudeLLM:
    """Claude through the official Anthropic SDK, with structured outputs.

    `output_config.format` constrains the reply to valid JSON matching the schema, so parsing
    never fails on shape; the invoice's business rules are still checked by the caller.

    One class serves the Anthropic API (AsyncAnthropic) and Amazon Bedrock
    (AsyncAnthropicBedrockMantle). If the model declines, the request is re-run on a fallback
    model: server-side (`fallbacks="default"`) on the Anthropic API, and through the SDK's
    client-side middleware on Bedrock (configured in factory.py).

    Not covered by the test suite: it needs credentials and spends real money per call.
    """

    def __init__(
        self,
        client: AsyncAnthropic | AsyncAnthropicBedrockMantle,
        *,
        name: str,
        model: str,
        effort: str,
        max_tokens: int,
        server_side_fallbacks: bool,
    ) -> None:
        self._client = client
        self.name = name
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self._server_side_fallbacks = server_side_fallbacks

    async def complete(
        self, system: str, messages: list[Message], json_schema: dict[str, Any]
    ) -> LLMResponse:
        options: dict[str, Any] = {}
        # The client-side fallback middleware pins fallbacks through this per-request state.
        fallback_scope: AbstractContextManager[Any] = BetaFallbackState()
        if self._server_side_fallbacks:
            options = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
            fallback_scope = nullcontext()

        with fallback_scope:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]  # role/content dicts
                output_config={
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": json_schema},
                },
                **options,
            )

        text = next((block.text for block in response.content if block.type == "text"), "")
        return LLMResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
            model=response.model,  # the model that actually answered, after any fallback
        )
