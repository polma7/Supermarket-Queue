import pytest

from supermarket_queue.service_time import compute_service_time_seconds


def test_compute_service_time_seconds():
    assert compute_service_time_seconds(basket_size=10, base_seconds=0.5, per_item_seconds=0.1) == 1.5


def test_compute_service_time_seconds_rejects_negative():
    with pytest.raises(ValueError):
        compute_service_time_seconds(basket_size=-1, base_seconds=0.0, per_item_seconds=0.0)

