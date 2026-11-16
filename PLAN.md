# PLAN — llm-document-extraction

Upload an invoice as text or PDF. An LLM extracts its fields into a strict Pydantic schema, and the output is validated, including business rules such as the totals adding up. If validation fails, the model gets one retry that includes the exact validation errors. Every extraction then goes to a human review queue, where a reviewer approves it or corrects fields. A script measures field-level accuracy against hand-labelled samples.

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pypdf, the Anthropic Python SDK, boto3, pytest, ruff, uv.

## Modules

| Module | Responsibility |
|---|---|
| documents | Upload a `.txt` or `.pdf`. Text is pulled out with pypdf; scanned PDFs with no text layer are rejected with `NO_TEXT`. The file is stored and the extraction runs straight away. Also list, get (with the text) and delete. |
| extractions | Calls the LLM with a JSON schema for the invoice, validates the result with the `Invoice` model, and retries once with the errors. Also list (filter by status), get, and re-run for a document. |
| reviews | The queue (extractions that are `pending_review` or `failed`), approve, and correct (partial field updates, re-validated, with a recorded diff). Also review history. |

**Providers (factory, chosen by config):**
- `StorageProvider`: local disk (default) or S3.
- `LLMProvider`: fake, Anthropic or Bedrock.
  - **Fake:** a deterministic rule-based parser, so tests and local runs need no key.
  - **Anthropic and Bedrock:** Claude through the official SDK on `claude-opus-5-5`, using structured outputs (`output_config.format` with a JSON Schema) so replies are always parseable JSON. Refusals fall back to another model: server-side on the Anthropic API, through the client-side middleware on Bedrock.

## Invoice schema

- **Header fields:** `invoice_number`, `invoice_date`, `due_date?`, `vendor_name`, `vendor_tax_id?`, `customer_name?`, `currency` (ISO 4217).
- **Amounts:** `subtotal?`, `tax?`, `total`.
- **`line_items`:** each has `description`, `quantity`, `unit_price` and `amount`.

**Business rules, checked after parsing:**
- quantity × unit_price = amount, for each line
- the line amounts add up to the subtotal
- subtotal + tax = total
- the due date is not before the invoice date

These rules are what makes the retry useful. Structured outputs guarantee the shape of the JSON, not that the numbers agree.

## Data model

```
documents    id, filename, content_type, size_bytes, storage_key, text, page_count?, created_at
extractions  id, document_id → documents, status (pending_review|failed|approved|corrected),
             data JSON?, attempts, first_errors JSON?, final_errors JSON?, raw_output,
             provider, model, input_tokens, output_tokens, created_at, updated_at
reviews      id, extraction_id → extractions, action (approve|correct), reviewer, changes JSON, created_at
```

## Accuracy script (no numbers in the README)

`scripts/evaluate.py` runs the configured provider over `eval/samples/*.txt` and compares the result with `eval/labels/*.json`. It reports per-field accuracy:
- strings are compared ignoring case and whitespace
- amounts are compared to the cent
- dates must match exactly
- line items are compared by count and amounts

The README's Results section will say only "Not yet measured, run …".

## Tests

- **Unit:** invoice validation rules, the fake parser, the retry loop (with a scripted LLM: invalid then valid, and invalid twice), correction diff and merge, PDF text extraction, settings, `start_with_secrets`.
- **Integration** (Postgres): upload txt and PDF (a PDF generated in the test with fpdf2), auto-extraction, the review queue, approve, correct (including a correction that breaks a rule, which is rejected), status rules, auth.

## Deployment files

The same set as the other repos. Postgres host port: **5445**.
