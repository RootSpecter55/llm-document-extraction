import json
import re
from datetime import datetime
from typing import Any

from app.providers.llm.base import LLMResponse, Message

_DOCUMENT = re.compile(r"<document>\n?(.*?)\n?</document>", re.S)
_AMOUNT = r"[^\d\n-]*(-?[\d,]+(?:\.\d+)?)"
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%B %d, %Y", "%d %b %Y")
_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}

# Label patterns, matched at the start of a line (case-insensitive).
_FIELDS = {
    "invoice_number": r"invoice\s*(?:number|no\.?|#)\s*[:#]?\s*(\S+)",
    "invoice_date": r"(?:invoice\s+)?date\s*:\s*(.+)",
    "due_date": r"(?:payment\s+)?due(?:\s+date)?\s*:\s*(.+)",
    "vendor_name": r"(?:from|vendor|seller|supplier)\s*:\s*(.+)",
    "vendor_tax_id": r"(?:tax\s*id|vat\s*(?:no\.?|number))\s*:\s*(.+)",
    "customer_name": r"(?:bill\s*to|customer)\s*:\s*(.+)",
    "currency": r"currency\s*:\s*([A-Za-z]{3})",
    "subtotal": r"sub\s*-?total\s*:" + _AMOUNT,
    "tax": r"(?:tax|vat)(?:\s*\([^)]*\))?\s*:" + _AMOUNT,
    "total": r"total(?:\s+due)?\s*:" + _AMOUNT,
}


def _find(pattern: str, text: str) -> str | None:
    match = re.search(rf"^\s*{pattern}\s*$", text, re.I | re.M)
    return match.group(1).strip() if match else None


def _number(value: str | None) -> float | None:
    return float(value.replace(",", "")) if value else None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return value  # left as-is: validation will report it


def parse_invoice_text(text: str) -> dict[str, Any]:
    """Rule-based extraction for invoices with "Label: value" lines and "a | b | c | d" items."""
    found = {field: _find(pattern, text) for field, pattern in _FIELDS.items()}
    currency = found["currency"]
    if not currency:
        currency = next((code for symbol, code in _SYMBOLS.items() if symbol in text), "")

    line_items = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            continue
        try:
            quantity, unit_price, amount = (
                float(p.replace(",", "").lstrip("$€£")) for p in parts[1:]
            )
        except ValueError:
            continue  # the header row, or not an item
        line_items.append(
            {
                "description": parts[0],
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": amount,
            }
        )

    return {
        "invoice_number": found["invoice_number"] or "",
        "invoice_date": _date(found["invoice_date"]) or "",
        "due_date": _date(found["due_date"]),
        "vendor_name": found["vendor_name"] or "",
        "vendor_tax_id": found["vendor_tax_id"],
        "customer_name": found["customer_name"],
        "currency": currency.upper(),
        "subtotal": _number(found["subtotal"]),
        "tax": _number(found["tax"]),
        "total": _number(found["total"]) or 0.0,
        "line_items": line_items,
    }


class FakeLLM:
    """Deterministic stand-in for a model: parses the document with regular expressions.

    It only understands simple "Label: value" invoices, which is enough for tests and local runs
    with no API key. It ignores retry feedback, so it returns the same answer on a retry.
    Token counts are word counts.
    """

    name = "fake"
    model = "fake-invoice-parser"

    async def complete(
        self, system: str, messages: list[Message], json_schema: dict[str, Any]
    ) -> LLMResponse:
        match = _DOCUMENT.search(messages[0]["content"])
        text = json.dumps(parse_invoice_text(match.group(1) if match else ""))
        prompt_words = len(system.split()) + sum(len(m["content"].split()) for m in messages)
        return LLMResponse(
            text=text,
            input_tokens=prompt_words,
            output_tokens=len(text.split()),
            stop_reason="end_turn",
            model=self.model,
        )
