import json
import re
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from fpdf import FPDF
from pydantic import ValidationError

from app.core.errors import AppError
from app.modules.documents.text_extraction import read_text
from app.modules.extractions.extractor import InvoiceExtractor, validate_output
from app.modules.extractions.invoice import Invoice
from app.modules.reviews.corrections import apply_corrections
from app.providers.llm.base import LLMResponse
from app.providers.llm.fake import parse_invoice_text
from scripts.start_with_secrets import SecretsError, load_secrets
from tests.conftest import INVOICE_TEXT

VALID = parse_invoice_text(INVOICE_TEXT)


class TestInvoiceRules:
    def test_accepts_a_consistent_invoice_and_stores_money_in_cents(self) -> None:
        invoice = Invoice.model_validate({**VALID, "tax": 85, "currency": "gbp"})
        assert invoice.tax == Decimal("85.00")
        assert invoice.currency == "GBP"

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"total": 600}, "subtotal + tax is 509.98, not total 600.00"),
            ({"subtotal": 400, "total": 485}, "line item amounts add up to 424.98"),
            ({"due_date": "2026-01-01"}, "due_date is before invoice_date"),
            ({"currency": "pounds"}, "String should match pattern"),
            ({"invoice_date": "14th of March"}, "Input should be a valid date"),
        ],
    )
    def test_rejects_values_that_disagree(self, change: dict[str, Any], message: str) -> None:
        with pytest.raises(ValidationError, match=re.escape(message)):
            Invoice.model_validate({**VALID, **change})

    def test_checks_each_line_item_multiplies_out(self) -> None:
        items = [{**VALID["line_items"][0], "amount": 250.0}, VALID["line_items"][1]]
        with pytest.raises(ValidationError, match="does not equal quantity x unit_price"):
            Invoice.model_validate({**VALID, "line_items": items})


class TestFakeParser:
    def test_reads_labelled_fields_and_pipe_separated_line_items(self) -> None:
        assert VALID["invoice_number"] == "INV-1001"
        assert VALID["due_date"] == "2026-04-13"
        assert VALID["vendor_tax_id"] == "GB123456789"
        assert len(VALID["line_items"]) == 2

    def test_understands_other_date_formats_labels_and_currency_symbols(self) -> None:
        text = (
            "Invoice No. A-7\nDate: 14 March 2026\nVendor: Globex\n"
            "Item | 1 | $10.00 | $10.00\nTotal: $10.00"
        )
        parsed = parse_invoice_text(text)
        assert parsed["invoice_number"] == "A-7"
        assert parsed["invoice_date"] == "2026-03-14"
        assert parsed["currency"] == "USD"
        assert parsed["customer_name"] is None and parsed["subtotal"] is None


class ScriptedLLM:
    name = "scripted"
    model = "scripted-model"

    def __init__(self, *responses: LLMResponse) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, system: str, messages: list, json_schema: dict) -> LLMResponse:
        self.calls += 1
        return self.responses.pop(0)


def answer(payload: Any, stop_reason: str = "end_turn") -> LLMResponse:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return LLMResponse(text, 10, 5, stop_reason, "m")


class TestExtractor:
    async def test_succeeds_first_time_without_a_retry(self) -> None:
        llm = ScriptedLLM(answer(VALID))
        outcome = await InvoiceExtractor(llm).extract("text")
        assert outcome.invoice is not None and outcome.attempts == 1 and llm.calls == 1

    async def test_retries_once_after_invalid_json(self) -> None:
        outcome = await InvoiceExtractor(ScriptedLLM(answer("{oops"), answer(VALID))).extract("t")
        assert outcome.invoice is not None
        assert outcome.attempts == 2
        assert outcome.first_errors and "not valid JSON" in outcome.first_errors[0]["message"]

    async def test_gives_up_after_the_retry(self) -> None:
        bad = {**VALID, "total": 1}
        outcome = await InvoiceExtractor(ScriptedLLM(answer(bad), answer(bad))).extract("t")
        assert outcome.invoice is None and outcome.attempts == 2
        assert outcome.final_errors == outcome.first_errors
        assert outcome.input_tokens == 20  # both attempts are counted

    async def test_does_not_retry_a_refusal(self) -> None:
        llm = ScriptedLLM(answer("", stop_reason="refusal"))
        outcome = await InvoiceExtractor(llm).extract("t")
        assert llm.calls == 1
        assert outcome.final_errors == [{"field": "", "message": "the model declined the request"}]


def test_validation_errors_name_the_field() -> None:
    _, errors = validate_output(json.dumps({**VALID, "currency": "dollars"}))
    assert errors[0]["field"] == "currency"


class TestCorrections:
    def test_records_only_fields_that_actually_changed(self) -> None:
        current = Invoice.model_validate(VALID).model_dump(mode="json")
        corrected, changes = apply_corrections(
            current, {"vendor_name": "Acme Ltd", "invoice_number": "INV-1001"}
        )
        assert corrected["vendor_name"] == "Acme Ltd"
        assert changes == {"vendor_name": {"from": "Acme Office Supplies Ltd", "to": "Acme Ltd"}}

    def test_rejects_unknown_fields_and_invalid_results(self) -> None:
        current = Invoice.model_validate(VALID).model_dump(mode="json")
        with pytest.raises(AppError) as unknown:
            apply_corrections(current, {"discount": 3})
        assert unknown.value.code == "UNKNOWN_FIELDS"
        with pytest.raises(AppError) as invalid:
            apply_corrections(current, {"total": 1})
        assert invalid.value.code == "INVALID_CORRECTION"


class TestReadText:
    def test_reads_utf8_text_and_rejects_other_encodings(self) -> None:
        assert read_text("a.txt", "Total: 5 €".encode()) == ("Total: 5 €", None)
        with pytest.raises(AppError, match="UTF-8"):
            read_text("a.txt", b"\xff\xfe")

    def test_reads_the_text_layer_of_a_pdf(self) -> None:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, "Invoice Number: PDF-1")
        text, pages = read_text("invoice.pdf", bytes(pdf.output()))
        assert "PDF-1" in text and pages == 1

    def test_rejects_other_file_types(self) -> None:
        with pytest.raises(AppError, match=r"Only \.txt and \.pdf"):
            read_text("invoice.png", b"...")


class TestStartWithSecrets:
    def test_requires_the_database_url_and_api_key(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": json.dumps({"API_KEY": "k"})}
        with pytest.raises(SecretsError, match="missing required keys: DATABASE_URL"):
            load_secrets({"SECRETS_SOURCE": "aws", "SECRET_ID": "s"}, client)

    def test_loads_a_complete_secret(self) -> None:
        client = MagicMock()
        secret = {"DATABASE_URL": "postgresql+asyncpg://x", "API_KEY": "k"}
        client.get_secret_value.return_value = {"SecretString": json.dumps(secret)}
        env = {"SECRETS_SOURCE": "aws", "SECRET_ID": "s"}
        load_secrets(env, client)
        assert env["API_KEY"] == "k"
