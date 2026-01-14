import random

import pytest

from supermarket_queue.arrival import sample_exponential_interarrival


def test_exponential_interarrival_requires_positive_rate():
    with pytest.raises(ValueError):
        sample_exponential_interarrival(rate_per_sec=0)


def test_exponential_interarrival_deterministic_with_rng():
    rng = random.Random(123)
    a = sample_exponential_interarrival(rate_per_sec=2.0, rng=rng)
    rng = random.Random(123)
    b = sample_exponential_interarrival(rate_per_sec=2.0, rng=rng)
    assert a == b
    assert a > 0

