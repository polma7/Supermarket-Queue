from __future__ import annotations

"""Arrival models for customer generation.

For a Poisson arrival process with rate λ (customers/second):
- The number of arrivals in a time window follows a Poisson distribution.
- The *inter-arrival times* are i.i.d. Exponential(λ).

In practice, we simulate this by repeatedly sampling an exponential waiting time
and sleeping that amount.
"""

import random


def sample_exponential_interarrival(*, rate_per_sec: float, rng: random.Random | None = None) -> float:
    """Sample the next inter-arrival time (seconds) for a Poisson process.

    Args:
        rate_per_sec: λ, the arrival rate in customers/second. Must be > 0.
        rng: optional RNG (useful for deterministic tests).

    Returns:
        A positive float representing seconds until the next arrival.

    Implementation detail:
        Python's `random.expovariate(lambd)` samples from an exponential
        distribution with parameter `lambd`.
    """
    if rate_per_sec <= 0:
        raise ValueError("rate_per_sec must be > 0")

    r = rng or random
    return float(r.expovariate(rate_per_sec))
