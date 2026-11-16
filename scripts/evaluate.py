"""Field-level accuracy of extractions against hand-labelled invoices.

    uv run python -m scripts.evaluate

Runs the configured LLM provider (LLM_PROVIDER, "fake" by default) over eval/samples/*.txt and
compares each result with eval/labels/<same name>.json. No server or database is needed.

Comparison rules:
  - text fields: equal after collapsing whitespace and ignoring case
  - amounts: equal to the cent;  dates: exactly equal;  missing (null) must match null
  - line_items: same number of items with the same amounts, in order
  - an extraction that failed validation counts as wrong for every field

With the fake provider this measures a regular-expression parser, not a language model; the
samples include layouts it cannot read on purpose.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
FIELDS = [
    "invoice_number",
    "invoice_date",
    "due_date",
    "vendor_name",
    "vendor_tax_id",
    "customer_name",
    "currency",
    "subtotal",
    "tax",
    "total",
    "line_items",
]


def normalise(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, list):
        return [item.amount for item in value]  # line items: compare amounts in order
    return value


async def main() -> None:
    load_dotenv(ROOT / ".env")
    # Imported after .env is loaded: settings are read on first use.
    from app.core.config import get_settings
    from app.modules.extractions.extractor import InvoiceExtractor
    from app.modules.extractions.invoice import Invoice
    from app.providers.llm.factory import create_llm

    settings = get_settings()
    extractor = InvoiceExtractor(create_llm(settings))
    correct = dict.fromkeys(FIELDS, 0)
    samples = sorted((ROOT / "eval" / "samples").glob("*.txt"))

    print(f"Provider: {settings.llm_provider}\n")
    print(f"{'sample':<16}{'status':<10}{'attempts':>9}  wrong fields")
    for sample in samples:
        label = Invoice.model_validate(
            json.loads((ROOT / "eval" / "labels" / f"{sample.stem}.json").read_text())
        )
        outcome = await extractor.extract(sample.read_text())
        wrong = []
        for field in FIELDS:
            expected = normalise(getattr(label, field))
            got = normalise(getattr(outcome.invoice, field)) if outcome.invoice else object()
            if got == expected:
                correct[field] += 1
            else:
                wrong.append(field)
        status = "valid" if outcome.invoice else "failed"
        print(f"{sample.stem:<16}{status:<10}{outcome.attempts:>9}  {', '.join(wrong) or '-'}")

    total = len(samples)
    print(f"\n{'field':<16}{'accuracy':>9}")
    for field in FIELDS:
        print(f"{field:<16}{correct[field] / total:>9.2f}")
    overall = sum(correct.values()) / (total * len(FIELDS))
    print(f"{'overall':<16}{overall:>9.2f}   ({total} samples x {len(FIELDS)} fields)")


if __name__ == "__main__":
    asyncio.run(main())
