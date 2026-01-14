"""Shared error envelope.

We keep error messages consistent across manager/checkout/customer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorResponse:
    code: str
    message: str

    def to_message(self, *, corr_id: str | None = None) -> dict[str, Any]:
        msg: dict[str, Any] = {"type": "error", "code": self.code, "message": self.message}
        if corr_id is not None:
            msg["corr_id"] = corr_id
        return msg

