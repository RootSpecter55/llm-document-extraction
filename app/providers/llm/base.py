from dataclasses import dataclass
from typing import Any, Protocol

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    model: str


class LLMProvider(Protocol):
    """Returns JSON text shaped by `json_schema`. Implementations: fake (default), Claude."""

    name: str
    model: str

    async def complete(
        self, system: str, messages: list[Message], json_schema: dict[str, Any]
    ) -> LLMResponse: ...
