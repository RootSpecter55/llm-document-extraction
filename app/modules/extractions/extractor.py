"""The extraction loop: ask the LLM, validate, and retry once with the validation errors."""

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.modules.extractions.invoice import LLM_OUTPUT_SCHEMA, Invoice
from app.providers.llm.base import LLMProvider, Message

SYSTEM_PROMPT = (
    "You extract data from invoices. Return JSON that matches the schema exactly. "
    "Use null for any field the document does not contain; never guess or invent values. "
    "Write dates as YYYY-MM-DD and currencies as ISO 4217 codes (for example USD, EUR, GBP). "
    "Copy amounts exactly as numbers, without currency symbols or thousands separators."
)

MAX_ATTEMPTS = 2  # the first try, plus one retry with the validation errors

ValidationErrors = list[dict[str, str]]


def document_prompt(text: str) -> str:
    return f"Extract the invoice fields from this document.\n\n<document>\n{text}\n</document>"


def retry_prompt(errors: ValidationErrors) -> str:
    lines = "\n".join(f"- {e['field'] or 'invoice'}: {e['message']}" for e in errors)
    return (
        "Your answer failed validation:\n"
        f"{lines}\n\n"
        "Re-read the document and return corrected JSON for the same invoice. "
        "Fix only what the document supports; use null where a value is not present."
    )


def validate_output(text: str) -> tuple[Invoice | None, ValidationErrors]:
    """Parses and validates model output; returns the invoice or a list of readable errors."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [{"field": "", "message": f"not valid JSON ({exc.msg})"}]
    try:
        return Invoice.model_validate(payload), []
    except ValidationError as exc:
        return None, [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]


@dataclass
class ExtractionOutcome:
    invoice: Invoice | None
    attempts: int
    first_errors: ValidationErrors | None
    final_errors: ValidationErrors | None
    raw_output: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list[Message] = field(default_factory=list)


class InvoiceExtractor:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    @property
    def provider_name(self) -> str:
        return self._llm.name

    async def extract(self, text: str) -> ExtractionOutcome:
        messages: list[Message] = [{"role": "user", "content": document_prompt(text)}]
        outcome = ExtractionOutcome(
            invoice=None,
            attempts=0,
            first_errors=None,
            final_errors=None,
            raw_output="",
            model=self._llm.model,
        )

        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = await self._llm.complete(SYSTEM_PROMPT, messages, LLM_OUTPUT_SCHEMA)
            outcome.attempts = attempt
            outcome.raw_output = response.text
            outcome.model = response.model
            outcome.input_tokens += response.input_tokens
            outcome.output_tokens += response.output_tokens

            if response.stop_reason == "refusal":
                # A declined request is not a formatting problem; retrying would not help.
                outcome.final_errors = [{"field": "", "message": "the model declined the request"}]
                break

            invoice, errors = validate_output(response.text)
            if invoice is not None:
                outcome.invoice = invoice
                outcome.final_errors = None
                break

            if attempt == 1:
                outcome.first_errors = errors
            outcome.final_errors = errors
            # Show the model its own answer and exactly what was wrong with it.
            messages = [
                *messages,
                {"role": "assistant", "content": response.text},
                {"role": "user", "content": retry_prompt(errors)},
            ]

        outcome.messages = messages
        return outcome


def invoice_to_json(invoice: Invoice) -> dict[str, Any]:
    """JSON-safe form for storage: decimals and dates become strings."""
    return invoice.model_dump(mode="json")
