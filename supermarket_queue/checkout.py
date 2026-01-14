from __future__ import annotations

# Checkout agent.
#
# In v0, checkouts are simple autonomous processes:
# - they register themselves with the manager
# - they periodically send a heartbeat
# - they repeatedly ask for the next customer assigned to them
# - they "serve" a customer by sleeping for service_seconds
#
# Normal operation feature:
# - the checkout publishes its own status periodically (so observers can monitor
#   the system without polling the manager).

import argparse
import time

from .mqtt_client import MqttClient
from .mqtt_topics import checkout_requests, checkout_responses, checkout_status
from .service_time import compute_service_time_seconds


def run_checkout(
    *,
    mqtt_host: str,
    mqtt_port: int,
    namespace: str,
    checkout_id: str,
    service_seconds: float,
    status_every: float = 2.0,
    base_seconds: float = 0.0,
    per_item_seconds: float = 0.0,
) -> None:
    # If base/per-item are provided, they override the old fixed `service_seconds`.
    # Backwards-compatible behavior:
    # - If per_item_seconds==0 and base_seconds==0, we fall back to fixed sleep.

    mqtt = MqttClient(client_id=f"checkout-{checkout_id}", host=mqtt_host, port=mqtt_port)
    mqtt.start()

    # Each checkout listens on its own response topic (point-to-point).
    reply_topic = checkout_responses(checkout_id, namespace)
    mqtt.subscribe(reply_topic)

    # Dedicated status topic (stream).
    status_topic = checkout_status(checkout_id, namespace)

    # Register with the manager.
    resp = mqtt.request(
        request_topic=checkout_requests(namespace),
        response_topic=reply_topic,
        message={
            "type": "register_checkout",
            "checkout_id": checkout_id,
            "service_seconds": service_seconds,
        },
        timeout=5.0,
    )
    if resp.get("type") != "checkout_registered":
        raise RuntimeError(f"Registration failed: {resp}")

    print(f"[checkout {checkout_id}] registered, service_seconds={service_seconds}")

    last_hb = 0.0
    last_status = 0.0
    served_count = 0

    while True:
        now = time.time()

        # Heartbeat is publish-only: the manager will mark you as alive.
        if now - last_hb >= 5:
            mqtt.publish(checkout_requests(namespace), {"type": "heartbeat", "checkout_id": checkout_id})
            last_hb = now

        # Publish operational status (normal feature).
        if now - last_status >= status_every:
            mqtt.publish(
                status_topic,
                {
                    "type": "checkout_status",
                    "checkout_id": checkout_id,
                    "service_seconds": service_seconds,
                    "base_seconds": base_seconds,
                    "per_item_seconds": per_item_seconds,
                    "served_count": served_count,
                    "ts": now,
                },
            )
            last_status = now

        # Ask the manager for the next customer in *your* queue.
        msg = mqtt.request(
            request_topic=checkout_requests(namespace),
            response_topic=reply_topic,
            message={"type": "checkout_next", "checkout_id": checkout_id},
            timeout=5.0,
        )

        customer = msg.get("customer")
        if customer is None:
            time.sleep(0.5)
            continue

        name = customer.get("name")
        basket_size = int(customer.get("basket_size", 0) or 0)

        if base_seconds > 0 or per_item_seconds > 0:
            st = compute_service_time_seconds(
                basket_size=basket_size,
                base_seconds=base_seconds,
                per_item_seconds=per_item_seconds,
            )
        else:
            # Old mode: fixed sleep.
            st = float(service_seconds)

        print(f"[checkout {checkout_id}] serving {name} (basket_size={basket_size}, service={st:0.2f}s)")
        time.sleep(st)
        served_count += 1
        print(f"[checkout {checkout_id}] done {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Checkout agent (MQTT)")
    parser.add_argument("--checkout-id", required=True)
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--namespace", default="supermarket/v0")

    # Backwards-compatible fixed service time.
    parser.add_argument("--service-seconds", type=float, default=2.0)

    # New per-customer model.
    parser.add_argument("--base-seconds", type=float, default=0.0, help="fixed overhead per customer")
    parser.add_argument("--per-item-seconds", type=float, default=0.0, help="seconds per grocery item")

    parser.add_argument(
        "--status-every",
        type=float,
        default=2.0,
        help="seconds between checkout status publications",
    )
    args = parser.parse_args()

    run_checkout(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        namespace=args.namespace,
        checkout_id=args.checkout_id,
        service_seconds=args.service_seconds,
        status_every=args.status_every,
        base_seconds=args.base_seconds,
        per_item_seconds=args.per_item_seconds,
    )


if __name__ == "__main__":
    main()
