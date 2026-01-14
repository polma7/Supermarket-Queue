from __future__ import annotations

# Customer generator (normal system component).
#
# This process simulates a stream of arriving customers and uses the exact same
# MQTT request/response protocol as the interactive `customer` CLI.
#
# Poisson arrival model:
# - Customers arrive according to a Poisson process with rate λ (customers/sec)
# - Inter-arrival times are exponential with mean 1/λ

import argparse
import time

from .arrival import sample_exponential_interarrival
from .mqtt_client import MqttClient
from .mqtt_topics import manager_requests, manager_responses


def run_generator(
    *,
    mqtt_host: str,
    mqtt_port: int,
    namespace: str,
    rate_per_sec: float,
    name_prefix: str = "Cust",
    max_customers: int | None = None,
    seed: int | None = None,
    mean_basket_size: float = 20.0,
) -> None:
    """Generate customers indefinitely (or for max_customers).

    Args:
        rate_per_sec: λ, customers per second.
        max_customers: if provided, stop after emitting this many customers.
        seed: if provided, makes arrivals deterministic.
        mean_basket_size: average number of items per customer.
    """
    import random

    rng = random.Random(seed) if seed is not None else None

    client_id = f"generator-{int(time.time())}"
    mqtt = MqttClient(client_id=client_id, host=mqtt_host, port=mqtt_port)
    mqtt.start()

    reply_topic = manager_responses(client_id, namespace)
    mqtt.subscribe(reply_topic)

    print(
        f"[generator] connected to MQTT {mqtt_host}:{mqtt_port}, namespace={namespace}, "
        f"rate={rate_per_sec} cust/s"
    )

    i = 0
    try:
        while True:
            if max_customers is not None and i >= max_customers:
                print(f"[generator] reached max_customers={max_customers}, stopping")
                return

            # Wait for the next arrival.
            dt = sample_exponential_interarrival(rate_per_sec=rate_per_sec, rng=rng)
            time.sleep(dt)

            i += 1
            name = f"{name_prefix}{i}"

            # Basket size model:
            # We use a Poisson-like discrete model. Python's standard library doesn't
            # have a Poisson sampler, so we approximate with a simple method when
            # mean is small, and fall back to a rounded exponential when mean is large.
            basket_size = _sample_basket_size(mean=mean_basket_size, rng=rng)

            resp = mqtt.request(
                request_topic=manager_requests(namespace),
                response_topic=reply_topic,
                message={"type": "join_queue", "name": name, "basket_size": basket_size},
                timeout=5.0,
            )

            if resp.get("type") == "assigned":
                print(
                    f"[generator] {name} items={basket_size} -> {resp['checkout_id']} "
                    f"(pos {resp['position']}, dt={dt:0.2f}s)"
                )
            else:
                print(f"[generator] {name} -> error {resp} (dt={dt:0.2f}s)")

    except KeyboardInterrupt:
        pass
    finally:
        mqtt.stop()


def _sample_basket_size(*, mean: float, rng) -> int:
    """Sample a non-negative integer basket size.

    We keep this dependency-free (no numpy).

    - For mean <= 30 we use Knuth's exact Poisson sampler.
    - For mean > 30 we approximate with a Gaussian N(mean, sqrt(mean)).

    This is good enough for a project simulation and stays lightweight.
    """
    import math
    import random

    r = rng or random
    if mean <= 0:
        return 0

    if mean <= 30:
        l = math.exp(-mean)
        k = 0
        p = 1.0
        while p > l:
            k += 1
            p *= r.random()
        return max(0, k - 1)

    return max(0, int(r.gauss(mean, math.sqrt(mean))))


def main() -> None:
    parser = argparse.ArgumentParser(description="Customer generator (Poisson arrivals over MQTT)")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--namespace", default="supermarket/v0")
    parser.add_argument(
        "--rate",
        type=float,
        required=True,
        help="arrival rate λ in customers/second (Poisson process)",
    )
    parser.add_argument("--name-prefix", default="Cust")
    parser.add_argument("--max-customers", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--mean-basket-size", type=float, default=20.0)
    args = parser.parse_args()

    run_generator(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        namespace=args.namespace,
        rate_per_sec=args.rate,
        name_prefix=args.name_prefix,
        max_customers=args.max_customers,
        seed=args.seed,
        mean_basket_size=args.mean_basket_size,
    )


if __name__ == "__main__":
    main()

