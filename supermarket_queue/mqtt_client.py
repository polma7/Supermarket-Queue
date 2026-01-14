"""Small MQTT helper built on top of paho-mqtt.

Why this exists:
- paho-mqtt is callback-based.
- For a small project it's convenient to also offer a *blocking request/response* helper.

Design:
- `MqttClient` manages connection + a background network loop.
- `request()` publishes a JSON message and waits for a correlated response.

Notes for students:
- MQTT is asynchronous by nature. The request/response pattern is built on top of it
  using a `corr_id` field and a dedicated response topic.
- QoS is kept at 0 for simplicity in v0.
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import paho.mqtt.client as mqtt


MessageHandler = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class PendingResponse:
    corr_id: str
    q: "queue.Queue[dict[str, Any]]"


class MqttClient:
    """Thin wrapper around paho-mqtt with JSON convenience APIs."""

    def __init__(
        self,
        *,
        client_id: str,
        host: str,
        port: int,
        keepalive: int = 30,
    ) -> None:
        self.client_id = client_id
        self.host = host
        self.port = port
        self.keepalive = keepalive

        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        self._client.on_message = self._on_message

        # External subscribers. Called with (topic, json_message).
        self._handlers: list[MessageHandler] = []

        # corr_id -> queue used by request()
        self._pending: dict[str, PendingResponse] = {}
        self._lock = threading.Lock()

        self._started = False

    def start(self) -> None:
        """Connect and start the background network loop."""
        if self._started:
            return
        self._client.connect(self.host, self.port, keepalive=self.keepalive)
        self._client.loop_start()
        self._started = True

    def stop(self) -> None:
        """Stop and disconnect."""
        if not self._started:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._started = False

    def add_handler(self, handler: MessageHandler) -> None:
        self._handlers.append(handler)

    def subscribe(self, topic: str) -> None:
        self._client.subscribe(topic, qos=0)

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._client.publish(topic, payload=payload, qos=0)

    def request(
        self,
        *,
        request_topic: str,
        response_topic: str,
        message: dict[str, Any],
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Publish a message and wait for a correlated response.

        The caller must ensure we are subscribed to `response_topic`.
        """
        corr_id = str(uuid.uuid4())
        msg = dict(message)
        msg["corr_id"] = corr_id
        msg["reply_to"] = response_topic

        q: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)
        pending = PendingResponse(corr_id=corr_id, q=q)

        with self._lock:
            self._pending[corr_id] = pending

        self.publish(request_topic, msg)

        try:
            return q.get(timeout=timeout)
        except queue.Empty as e:
            raise TimeoutError(f"No response for corr_id={corr_id}") from e
        finally:
            with self._lock:
                self._pending.pop(corr_id, None)

    # -------------------- internal callbacks --------------------

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        # Decode JSON (ignore malformed messages in v0).
        #
        # Depending on paho-mqtt version / type stubs, msg.payload may be `bytes` (typical)
        # or a `str`. We normalize to text before JSON parsing.
        try:
            raw = msg.payload
            if isinstance(raw, bytes):
                payload = raw.decode("utf-8")
            else:
                payload = str(raw)
            data = json.loads(payload)
        except Exception:
            return
        if not isinstance(data, dict):
            return

        # First, try to match pending request.
        corr_id = data.get("corr_id")
        if isinstance(corr_id, str):
            with self._lock:
                pending = self._pending.get(corr_id)
            if pending is not None:
                try:
                    pending.q.put_nowait(data)
                except queue.Full:
                    pass
                return

        # Otherwise broadcast to handlers.
        for h in list(self._handlers):
            try:
                h(msg.topic, data)
            except Exception:
                # In v0 we swallow handler exceptions to keep the client alive.
                continue
