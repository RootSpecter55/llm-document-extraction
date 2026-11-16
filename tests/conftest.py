"""Test configuration. The environment is set before any app module reads settings."""

import os
import tempfile

os.environ.update(
    {
        "APP_ENV": "test",
        "LOG_LEVEL": "WARNING",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5445/extraction_test"
        ),
        "API_KEY": "test-api-key-that-is-at-least-32-characters",
        "STORAGE_PROVIDER": "local",
        "LOCAL_STORAGE_DIR": tempfile.mkdtemp(prefix="extraction-test-uploads-"),
        "LLM_PROVIDER": "fake",
    }
)

INVOICE_TEXT = """INVOICE
Invoice Number: INV-1001
Invoice Date: 2026-03-14
Due Date: 2026-04-13
From: Acme Office Supplies Ltd
Tax ID: GB123456789
Bill To: Northwind Labs
Currency: GBP

Description | Qty | Unit Price | Amount
A4 paper (box) | 10 | 24.50 | 245.00
Toner cartridge | 2 | 89.99 | 179.98

Subtotal: 424.98
Tax: 85.00
Total: 509.98
"""
