"""The invoice schema: what an extraction must produce, and the rules it must satisfy."""

from datetime import date
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Amounts are compared to the cent: 0.01 absorbs rounding in "qty x price" lines.
TOLERANCE = Decimal("0.01")


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def amount_matches(self) -> Self:
        expected = self.quantity * self.unit_price
        if abs(expected - self.amount) > TOLERANCE:
            raise ValueError(
                f"amount {self.amount} does not equal quantity x unit_price ({expected})"
            )
        return self


class Invoice(BaseModel):
    """Field types catch malformed values; the validators below catch numbers that disagree."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str = Field(min_length=1)
    invoice_date: date
    due_date: date | None = None
    vendor_name: str = Field(min_length=1)
    vendor_tax_id: str | None = None
    customer_name: str | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$", description="ISO 4217 code, e.g. USD")
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    total: Decimal = Field(ge=0)
    line_items: list[LineItem] = Field(default_factory=list)

    @field_validator("currency", mode="before")
    @classmethod
    def upper_currency(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def totals_add_up(self) -> Self:
        problems = []
        if self.due_date and self.due_date < self.invoice_date:
            problems.append("due_date is before invoice_date")
        if self.line_items and self.subtotal is not None:
            lines = sum((item.amount for item in self.line_items), Decimal(0))
            if abs(lines - self.subtotal) > TOLERANCE:
                problems.append(
                    f"line item amounts add up to {lines}, not subtotal {self.subtotal}"
                )
        if self.subtotal is not None:
            expected = self.subtotal + (self.tax or Decimal(0))
            if abs(expected - self.total) > TOLERANCE:
                problems.append(f"subtotal + tax is {expected}, not total {self.total}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


# The JSON Schema given to the LLM (structured outputs). It describes the shape only; the
# business rules above are checked after parsing, and their errors drive the retry.
LLM_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
        "due_date": _nullable({"type": "string", "description": "YYYY-MM-DD"}),
        "vendor_name": {"type": "string"},
        "vendor_tax_id": _nullable({"type": "string"}),
        "customer_name": _nullable({"type": "string"}),
        "currency": {"type": "string", "description": "ISO 4217 code such as USD, EUR, GBP"},
        "subtotal": _nullable({"type": "number"}),
        "tax": _nullable({"type": "number"}),
        "total": {"type": "number"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "amount": {"type": "number"},
                },
                "required": ["description", "quantity", "unit_price", "amount"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
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
    ],
    "additionalProperties": False,
}
