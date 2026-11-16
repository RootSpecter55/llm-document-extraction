from typing import Any

from pydantic import ValidationError

from app.core.errors import AppError
from app.modules.extractions.extractor import invoice_to_json
from app.modules.extractions.invoice import Invoice


def apply_corrections(
    current: dict[str, Any] | None, fields: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merges the reviewer's fields over the current data and re-validates the whole invoice.

    Returns (new data, changes), where changes maps each field whose value actually changed to
    {"from": old, "to": new}. Raises a 400 listing the problems if the result is not a valid
    invoice, so a correction can never store numbers that do not add up.
    """
    unknown = sorted(set(fields) - set(Invoice.model_fields))
    if unknown:
        raise AppError(400, "UNKNOWN_FIELDS", "These are not invoice fields", {"fields": unknown})

    base = current or {}
    try:
        corrected = invoice_to_json(Invoice.model_validate({**base, **fields}))
    except ValidationError as exc:
        problems = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        raise AppError(
            400, "INVALID_CORRECTION", "The corrected invoice is not valid", problems
        ) from exc

    changes = {
        name: {"from": base.get(name), "to": value}
        for name, value in corrected.items()
        if base.get(name) != value
    }
    return corrected, changes
