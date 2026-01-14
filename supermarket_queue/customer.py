from __future__ import annotations

# Customer client.
#
# A customer is a short-lived process in v0:
# - connect to broker
# - publish a join_queue request
# - wait for an assignment response
# - print the assignment and exit

import argparse
import time

from .mqtt_client import MqttClient
from .mqtt_topics import manager_requests, manager_responses


def join_queue(*, mqtt_host: str, mqtt_port: int, namespace: str, name: str, basket_size: int = 0) -> dict:
    # Use a unique client id so multiple customers can run concurrently.
    client_id = f"customer-{name}-{int(time.time() * 1000)}"
    mqtt = MqttClient(client_id=client_id, host=mqtt_host, port=mqtt_port)
    mqtt.start()

    # Customer listens for its response on a dedicated topic.
    reply_topic = manager_responses(client_id, namespace)
    mqtt.subscribe(reply_topic)

    try:
        return mqtt.request(
            request_topic=manager_requests(namespace),
            response_topic=reply_topic,
            message={"type": "join_queue", "name": name, "basket_size": int(basket_size)},
            timeout=5.0,
        )
    finally:
        mqtt.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Customer client (MQTT)")
    parser.add_argument("--name", required=True)
    parser.add_argument("--basket-size", type=int, default=0, help="number of grocery items")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--namespace", default="supermarket/v0")
    args = parser.parse_args()

    resp = join_queue(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        namespace=args.namespace,
        name=args.name,
        basket_size=args.basket_size,
    )
    if resp.get("type") == "assigned":
        print(
            f"[customer {args.name}] assigned to {resp['checkout_id']} (position {resp['position']})"
        )
    else:
        print(f"[customer {args.name}] error: {resp}")


if __name__ == "__main__":
    main()
