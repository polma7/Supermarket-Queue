from __future__ import annotations

# The Queue Manager is the *authoritative brain* of the system in v0.
#
# IMPORTANT: This file contains two layers:
# 1) `QueueManager` (pure logic, easy to unit test)
# 2) `MqttQueueManagerService` + `main()` (integration with MQTT broker)

import argparse
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .errors import ErrorResponse

if TYPE_CHECKING:
    from .mqtt_client import MqttClient


@dataclass
class CheckoutState:
    """In-memory state for one checkout."""

    checkout_id: str
    service_seconds: float
    queue: list[dict[str, Any]] = field(default_factory=list)  # customers in FIFO order
    last_seen: float = field(default_factory=time.time)


class QueueManager:
    """Core business logic (testable without MQTT)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._checkouts: dict[str, CheckoutState] = {}

        # Round-robin pointer to break ties fairly when multiple checkouts have
        # the same predicted workload.
        self._rr_index: int = 0

    # -------------------- checkout lifecycle --------------------

    def register_checkout(self, checkout_id: str, service_seconds: float) -> None:
        """Create/overwrite a checkout state."""
        with self._lock:
            self._checkouts[checkout_id] = CheckoutState(
                checkout_id=checkout_id, service_seconds=service_seconds
            )

    def notify_heartbeat(self, checkout_id: str) -> None:
        """Update the liveness timestamp for a checkout."""
        with self._lock:
            st = self._checkouts.get(checkout_id)
            if st:
                st.last_seen = time.time()

    # -------------------- queue operations --------------------

    def status(self) -> dict[str, Any]:
        """Return current sizes of all queues."""
        with self._lock:
            return {
                "type": "status_response",
                "checkouts": {
                    cid: {
                        "service_seconds": st.service_seconds,
                        "queue_len": len(st.queue),
                        "last_seen": st.last_seen,
                    }
                    for cid, st in self._checkouts.items()
                },
            }

    def assign_customer(self, customer: dict[str, Any]) -> tuple[str, int]:
        """Assign a customer to the best checkout.

        Policy: choose checkout with smallest predicted workload.

        Tie-breaking: if multiple checkouts have equal minimal workload, use
        round-robin over those candidates to avoid systematic bias towards low
        checkout IDs.
        """
        with self._lock:
            if not self._checkouts:
                raise ValueError("no_checkouts")

            # Compute workload per checkout.
            scored: list[tuple[float, str, CheckoutState]] = []
            for st in self._checkouts.values():
                items_sum = 0
                for c in st.queue:
                    try:
                        items_sum += int(c.get("basket_size", 0) or 0)
                    except Exception:
                        continue
                w = float(items_sum + len(st.queue))
                scored.append((w, st.checkout_id, st))

            # Find minimal workload.
            min_w = min(s[0] for s in scored)
            candidates = [s for s in scored if s[0] == min_w]

            # Deterministic ordering of candidates for stable round-robin.
            candidates.sort(key=lambda t: t[1])  # sort by checkout_id

            chosen_tuple = candidates[self._rr_index % len(candidates)]
            self._rr_index += 1

            chosen = chosen_tuple[2]
            chosen.queue.append(customer)
            return chosen.checkout_id, len(chosen.queue)

    def next_customer(self, checkout_id: str) -> dict[str, Any] | None:
        """Pop the next customer from a specific checkout queue."""
        with self._lock:
            st = self._checkouts.get(checkout_id)
            if st is None:
                raise KeyError("unknown_checkout")
            if not st.queue:
                return None
            return st.queue.pop(0)


class MqttQueueManagerService:
    """MQTT adapter around the QueueManager business logic."""

    def __init__(self, *, mqtt: MqttClient, namespace: str = "supermarket/v0") -> None:
        # Local imports so unit tests can import QueueManager without paho-mqtt.
        from .mqtt_topics import checkout_requests, manager_requests, status_updates

        self._checkout_requests = checkout_requests
        self._manager_requests = manager_requests
        self._status_updates = status_updates

        self.mqtt = mqtt
        self.namespace = namespace
        self.manager = QueueManager()

        # Background publisher thread control.
        self._stop_event = threading.Event()
        self._status_thread: threading.Thread | None = None

    def start(self, *, publish_status_every: float = 2.0) -> None:
        # Subscribe to two shared request topics.
        self.mqtt.subscribe(self._manager_requests(self.namespace))
        self.mqtt.subscribe(self._checkout_requests(self.namespace))

        # Also subscribe to all per-checkout status streams.
        # In v0 we don't use them for decision-making yet, but they are part of
        # the normal observability of the system.
        self.mqtt.subscribe(f"{self.namespace}/checkouts/status/+")

        self.mqtt.add_handler(self._handle_message)

        # Start periodic publisher for observers.
        self._status_thread = threading.Thread(
            target=self._status_publisher_loop,
            args=(publish_status_every,),
            daemon=True,
        )
        self._status_thread.start()

    def stop(self) -> None:
        """Stop background threads. Call before disconnecting MQTT."""
        self._stop_event.set()
        t = self._status_thread
        if t and t.is_alive():
            t.join(timeout=1.0)

    def _status_publisher_loop(self, interval: float) -> None:
        """Publish periodic status updates for observers.

        Observers can subscribe to a single topic and display a live dashboard.
        """
        while not self._stop_event.is_set():
            try:
                snapshot = self.manager.status()
                self.mqtt.publish(self._status_updates(self.namespace), snapshot)
            except Exception:
                # Keep publishing even if an occasional error occurs.
                pass
            self._stop_event.wait(interval)

    def _reply(self, reply_to: str, corr_id: str | None, message: dict[str, Any]) -> None:
        msg = dict(message)
        if corr_id is not None:
            msg["corr_id"] = corr_id
        self.mqtt.publish(reply_to, msg)

    def _handle_message(self, topic: str, msg: dict[str, Any]) -> None:
        # Note: this handler processes:
        # - request/response messages from customers and checkouts
        # - streaming status messages from checkouts (currently ignored)

        mtype = msg.get("type")

        corr_id = msg.get("corr_id") if isinstance(msg.get("corr_id"), str) else None
        reply_to = msg.get("reply_to") if isinstance(msg.get("reply_to"), str) else None

        # -------- checkout requests --------
        if mtype == "register_checkout":
            if not reply_to:
                return
            checkout_id = str(msg.get("checkout_id", ""))
            if not checkout_id:
                self._reply(
                    reply_to,
                    corr_id,
                    ErrorResponse("bad_request", "checkout_id required").to_message(),
                )
                return
            service_seconds = float(msg.get("service_seconds", 2.0))
            self.manager.register_checkout(checkout_id, service_seconds)
            self._reply(reply_to, corr_id, {"type": "checkout_registered", "checkout_id": checkout_id})
            return

        if mtype == "heartbeat":
            checkout_id = str(msg.get("checkout_id", ""))
            if checkout_id:
                self.manager.notify_heartbeat(checkout_id)
            return

        if mtype == "checkout_next":
            if not reply_to:
                return
            checkout_id = str(msg.get("checkout_id", ""))
            if not checkout_id:
                self._reply(
                    reply_to,
                    corr_id,
                    ErrorResponse("bad_request", "checkout_id required").to_message(),
                )
                return
            try:
                customer = self.manager.next_customer(checkout_id)
            except KeyError:
                self._reply(
                    reply_to,
                    corr_id,
                    ErrorResponse("unknown_checkout", "Unregistered checkout").to_message(),
                )
                return
            self._reply(reply_to, corr_id, {"type": "next_customer", "customer": customer})
            return

        # -------- customer requests --------
        if mtype == "join_queue":
            if not reply_to:
                return
            name = str(msg.get("name", ""))
            if not name:
                self._reply(reply_to, corr_id, ErrorResponse("bad_request", "name required").to_message())
                return

            basket_size = int(msg.get("basket_size", 0) or 0)
            if basket_size < 0:
                basket_size = 0

            customer = {"name": name, "basket_size": basket_size, "ts": time.time()}
            try:
                checkout_id, position = self.manager.assign_customer(customer)
            except ValueError:
                self._reply(reply_to, corr_id, ErrorResponse("no_checkouts", "No checkouts available").to_message())
                return
            self._reply(
                reply_to,
                corr_id,
                {
                    "type": "assigned",
                    "name": name,
                    "basket_size": basket_size,
                    "checkout_id": checkout_id,
                    "position": position,
                },
            )
            return

        # (Cleaned) No request/response 'status' endpoint.
        # The manager broadcasts periodic status snapshots on `<ns>/status/updates`
        # and the GUI subscribes to that stream.


def main() -> None:
    # Import MQTT dependencies only when running the real service.
    from .mqtt_client import MqttClient

    parser = argparse.ArgumentParser(description="Queue Manager (MQTT)")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--namespace", default="supermarket/v0")
    parser.add_argument(
        "--publish-status-every",
        type=float,
        default=2.0,
        help="seconds between broadcast status updates (observer dashboard)",
    )
    args = parser.parse_args()

    mqtt_client = MqttClient(client_id="manager", host=args.mqtt_host, port=args.mqtt_port)
    mqtt_client.start()

    service = MqttQueueManagerService(mqtt=mqtt_client, namespace=args.namespace)
    service.start(publish_status_every=args.publish_status_every)

    print(f"[manager] connected to MQTT {args.mqtt_host}:{args.mqtt_port}, namespace={args.namespace}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        mqtt_client.stop()


if __name__ == "__main__":
    main()

