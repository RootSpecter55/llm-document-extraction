from typing import Any

from fpdf import FPDF
from httpx import ASGITransport, AsyncClient

from app.container import build_container
from app.core.config import get_settings
from app.main import create_app
from app.providers.llm.base import LLMResponse
from tests.conftest import INVOICE_TEXT
from tests.integration.conftest import API, upload


def make_pdf(text: str | None) -> bytes:
    """A real PDF built in the test: with a text layer, or blank (like a scanned page)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in (text or "").splitlines():
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


async def test_requires_the_api_key(client: AsyncClient) -> None:
    assert (await client.get("/documents")).status_code == 401
    assert (await client.get("/health")).status_code == 200


async def test_extracts_a_text_invoice_into_the_review_queue(client: AsyncClient) -> None:
    result = await upload(client, INVOICE_TEXT.encode())
    extraction = result["extraction"]

    assert extraction["status"] == "pending_review"
    assert extraction["attempts"] == 1 and extraction["firstErrors"] is None
    data = extraction["data"]
    assert data["invoice_number"] == "INV-1001"
    assert data["invoice_date"] == "2026-03-14"
    assert data["currency"] == "GBP"
    assert data["total"] == "509.98"
    assert [item["description"] for item in data["line_items"]] == [
        "A4 paper (box)",
        "Toner cartridge",
    ]

    queue = await client.get("/reviews/queue", headers=API)
    assert [e["id"] for e in queue.json()["data"]] == [extraction["id"]]


async def test_extracts_from_a_pdf_text_layer(client: AsyncClient) -> None:
    result = await upload(client, make_pdf(INVOICE_TEXT), "invoice.pdf")
    assert result["document"]["pageCount"] == 1
    assert result["extraction"]["data"]["vendor_name"] == "Acme Office Supplies Ltd"

    document = await client.get(f"/documents/{result['document']['id']}", headers=API)
    assert "INV-1001" in document.json()["data"]["text"]


async def test_rejects_unreadable_and_unsupported_files(client: AsyncClient) -> None:
    async def status(filename: str, content: bytes) -> tuple[int, str]:
        response = await client.post(
            "/documents", headers=API, files={"file": (filename, content, "application/pdf")}
        )
        return response.status_code, response.json()["error"]["code"]

    assert await status("scan.pdf", make_pdf(None)) == (422, "NO_TEXT")
    assert await status("broken.pdf", b"not a pdf") == (400, "INVALID_PDF")
    assert await status("invoice.docx", b"PK...") == (400, "UNSUPPORTED_FILE_TYPE")
    assert await status("long.txt", b"x" * 50_001) == (413, "DOCUMENT_TOO_LONG")


async def test_an_invoice_whose_totals_do_not_add_up_fails_after_one_retry(
    client: AsyncClient,
) -> None:
    broken = INVOICE_TEXT.replace("Total: 509.98", "Total: 600.00")
    extraction = (await upload(client, broken.encode()))["extraction"]

    assert extraction["status"] == "failed"
    assert extraction["attempts"] == 2
    assert extraction["data"] is None
    assert "subtotal + tax is 509.98, not total 600.00" in extraction["finalErrors"][0]["message"]

    queue = await client.get("/reviews/queue", headers=API)
    assert queue.json()["data"][0]["status"] == "failed"


class ScriptedLLM:
    """Returns prepared answers in order and records every request it received."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.requests: list[list[dict[str, str]]] = []

    async def complete(self, system: str, messages: list[dict[str, str]], json_schema: Any):
        self.requests.append(messages)
        return LLMResponse(self.answers.pop(0), 100, 50, "end_turn", self.model)


async def test_the_retry_shows_the_model_its_errors_and_accepts_a_fixed_answer() -> None:
    import json

    from app.providers.llm.fake import parse_invoice_text

    good = parse_invoice_text(INVOICE_TEXT)
    wrong_currency = {**good, "currency": "pounds"}
    llm = ScriptedLLM(json.dumps(wrong_currency), json.dumps(good))

    app = create_app(build_container(get_settings(), llm=llm))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        extraction = (await upload(c, INVOICE_TEXT.encode()))["extraction"]

    assert extraction["status"] == "pending_review"
    assert extraction["attempts"] == 2
    assert extraction["firstErrors"][0]["field"] == "currency"
    assert extraction["inputTokens"] == 200 and extraction["outputTokens"] == 100

    retry = llm.requests[1]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert retry[1]["content"] == json.dumps(wrong_currency)
    assert "currency" in retry[2]["content"] and "failed validation" in retry[2]["content"]


async def test_approving_removes_an_extraction_from_the_queue(client: AsyncClient) -> None:
    extraction = (await upload(client, INVOICE_TEXT.encode()))["extraction"]
    path = f"/extractions/{extraction['id']}"

    review = await client.post(f"{path}/approve", headers=API, json={"reviewer": "dana"})
    assert review.status_code == 201
    assert review.json()["data"]["action"] == "approve"
    assert (await client.get(path, headers=API)).json()["data"]["status"] == "approved"
    assert (await client.get("/reviews/queue", headers=API)).json()["meta"]["total"] == 0

    again = await client.post(f"{path}/approve", headers=API, json={"reviewer": "dana"})
    assert again.status_code == 409
    corrected = await client.post(
        f"{path}/corrections", headers=API, json={"reviewer": "dana", "fields": {"tax": 1}}
    )
    assert corrected.status_code == 409


async def test_corrections_are_revalidated_and_recorded_as_a_diff(client: AsyncClient) -> None:
    extraction = (await upload(client, INVOICE_TEXT.encode()))["extraction"]
    path = f"/extractions/{extraction['id']}/corrections"

    # Changing tax alone would break subtotal + tax = total, so it is rejected...
    rejected = await client.post(
        path, headers=API, json={"reviewer": "dana", "fields": {"tax": 90}}
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "INVALID_CORRECTION"
    unchanged = await client.get(f"/extractions/{extraction['id']}", headers=API)
    assert unchanged.json()["data"]["status"] == "pending_review"

    # ...but changing tax and total together is consistent.
    review = await client.post(
        path,
        headers=API,
        json={
            "reviewer": "dana",
            "fields": {"tax": 90, "total": 514.98, "customer_name": "NW Labs"},
        },
    )
    assert review.status_code == 201
    assert review.json()["data"]["changes"] == {
        "tax": {"from": "85.00", "to": "90.00"},
        "total": {"from": "509.98", "to": "514.98"},
        "customer_name": {"from": "Northwind Labs", "to": "NW Labs"},
    }
    saved = (await client.get(f"/extractions/{extraction['id']}", headers=API)).json()["data"]
    assert saved["status"] == "corrected" and saved["data"]["total"] == "514.98"

    history = await client.get(f"/reviews?extractionId={extraction['id']}", headers=API)
    assert history.json()["meta"]["total"] == 1


async def test_rejects_corrections_to_fields_that_do_not_exist(client: AsyncClient) -> None:
    extraction = (await upload(client, INVOICE_TEXT.encode()))["extraction"]
    response = await client.post(
        f"/extractions/{extraction['id']}/corrections",
        headers=API,
        json={"reviewer": "dana", "fields": {"discount": 5}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"] == {"fields": ["discount"]}


async def test_a_failed_extraction_can_be_completed_by_a_reviewer(client: AsyncClient) -> None:
    from app.providers.llm.fake import parse_invoice_text

    broken = INVOICE_TEXT.replace("Total: 509.98", "Total: 600.00")
    extraction = (await upload(client, broken.encode()))["extraction"]
    fields = parse_invoice_text(INVOICE_TEXT)  # the reviewer supplies the full, correct invoice

    response = await client.post(
        f"/extractions/{extraction['id']}/corrections",
        headers=API,
        json={"reviewer": "dana", "fields": fields},
    )
    assert response.status_code == 201
    saved = (await client.get(f"/extractions/{extraction['id']}", headers=API)).json()["data"]
    assert saved["status"] == "corrected" and saved["data"]["invoice_number"] == "INV-1001"


async def test_rerun_and_delete(client: AsyncClient) -> None:
    result = await upload(client, INVOICE_TEXT.encode())
    document_id = result["document"]["id"]

    again = await client.post(f"/documents/{document_id}/extractions", headers=API)
    assert again.status_code == 201
    listed = await client.get(f"/extractions?documentId={document_id}", headers=API)
    assert listed.json()["meta"]["total"] == 2

    assert (await client.delete(f"/documents/{document_id}", headers=API)).status_code == 204
    assert (
        await client.get(f"/extractions/{again.json()['data']['id']}", headers=API)
    ).status_code == 404
