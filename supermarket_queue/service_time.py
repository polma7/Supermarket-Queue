from __future__ import annotations

# Service time helpers.
#
# We model the time it takes to scan/process a customer's groceries.
# This is intentionally simple and configurable:
#   service_time_seconds = base_seconds + per_item_seconds * basket_size
#
# This gives you:
# - a fixed overhead (paying, bagging, etc.)
# - a per-item scanning time


def compute_service_time_seconds(*, basket_size: int, base_seconds: float, per_item_seconds: float) -> float:
    """Compute how long a checkout should take for a single customer.

    Args:
        basket_size: number of grocery items for the customer (>= 0).
        base_seconds: fixed overhead time (>= 0).
        per_item_seconds: time per item scanned (>= 0).

    Returns:
        Non-negative float.
    """
    if basket_size < 0:
        raise ValueError("basket_size must be >= 0")
    if base_seconds < 0:
        raise ValueError("base_seconds must be >= 0")
    if per_item_seconds < 0:
        raise ValueError("per_item_seconds must be >= 0")

    return float(base_seconds + per_item_seconds * basket_size)

