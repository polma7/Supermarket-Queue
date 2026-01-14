from __future__ import annotations

# Simple GUI dashboard (Tkinter).
#
# Goal: show the same information as the observer CLI, but in a small window.
# We keep it dependency-free by using Tkinter (ships with most Python installs).
#
# Architecture:
# - MQTT callbacks run on a background thread managed by paho-mqtt.
# - Tkinter must be updated from the main UI thread.
# - We therefore push incoming status snapshots into a Queue and poll it via
#   `root.after(...)`.

import argparse
import queue
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, cast

from .mqtt_client import MqttClient
from .mqtt_topics import status_updates


class DashboardApp:
    def __init__(self, *, mqtt_host: str, mqtt_port: int, namespace: str, refresh_ms: int = 250) -> None:
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.namespace = namespace
        self.refresh_ms = refresh_ms

        self.root = tk.Tk()
        self.root.title("Supermarket Queue Dashboard")
        self.root.geometry("720x420")

        # Top info bar
        self.info_var = tk.StringVar(value="Connecting...")
        info = ttk.Label(self.root, textvariable=self.info_var)
        info.pack(fill=cast(Any, tk.X), padx=10, pady=(10, 5))

        # Table of checkouts
        cols = ("checkout_id", "queue_len", "served_count", "last_seen")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=12)
        self.tree.heading("checkout_id", text="Checkout")
        self.tree.heading("queue_len", text="Queue length")
        self.tree.heading("served_count", text="Served customers")
        self.tree.heading("last_seen", text="Last seen")

        self.tree.column("checkout_id", width=120, anchor=cast(Any, tk.W))
        self.tree.column("queue_len", width=110, anchor=cast(Any, tk.E))
        self.tree.column("served_count", width=140, anchor=cast(Any, tk.E))
        self.tree.column("last_seen", width=160, anchor=cast(Any, tk.W))

        self.tree.pack(fill=cast(Any, tk.BOTH), expand=True, padx=10, pady=10)

        # Bottom help
        help_text = "Live updates from MQTT topic: " + status_updates(namespace)
        ttk.Label(self.root, text=help_text).pack(fill=cast(Any, tk.X), padx=10, pady=(0, 10))

        # Incoming status snapshots from MQTT thread
        self._inbox: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=5)

        # MQTT client
        self._mqtt = MqttClient(client_id=f"gui-{int(time.time())}", host=mqtt_host, port=mqtt_port)

        # Track whether we actually received any status snapshots.
        self._last_snapshot_ts: float | None = None

        # Per-checkout served counters (reported by checkout agents).
        self._served_by_checkout: dict[str, int] = {}

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def start(self) -> None:
        # Connect to MQTT. If broker isn't reachable, keep UI alive and show error.
        try:
            self._mqtt.start()

            # Aggregated snapshots from manager.
            self._mqtt.subscribe(status_updates(self.namespace))

            # Per-checkout status events (served_count, etc.).
            # Using '+' wildcard to receive all checkouts.
            self._mqtt.subscribe(f"{self.namespace}/checkouts/status/+")

            self._mqtt.add_handler(self._on_mqtt_message)
            self.info_var.set(
                f"Connected to MQTT {self.mqtt_host}:{self.mqtt_port} | namespace={self.namespace} | waiting for updates..."
            )
        except Exception as e:
            self.info_var.set(f"MQTT connection failed: {e}")

        # Start UI polling
        self.root.after(cast(Any, self.refresh_ms), self._drain_inbox)
        self.root.mainloop()

    def close(self) -> None:
        try:
            self._mqtt.stop()
        finally:
            self.root.destroy()

    # -------------------- MQTT thread callback --------------------

    def _on_mqtt_message(self, topic: str, msg: dict[str, Any]) -> None:
        # We handle two message types:
        # - status_response (manager snapshot): drives the table
        # - checkout_status (checkout telemetry): updates served counters

        mtype = msg.get("type")

        if mtype == "checkout_status":
            cid = msg.get("checkout_id")
            served = msg.get("served_count")
            if isinstance(cid, str) and isinstance(served, int):
                self._served_by_checkout[cid] = served
            return

        if mtype != "status_response":
            return

        try:
            self._inbox.put_nowait(msg)
        except queue.Full:
            # Drop oldest UI updates if UI is slow.
            pass

    # -------------------- UI thread polling --------------------

    def _drain_inbox(self) -> None:
        latest: dict[str, Any] | None = None
        while True:
            try:
                latest = self._inbox.get_nowait()
            except queue.Empty:
                break

        if latest is not None:
            self._last_snapshot_ts = time.time()
            self._render_status(latest)
        else:
            # If we haven't received anything yet, keep the UI informative.
            if self._last_snapshot_ts is None:
                self.info_var.set(
                    f"Connected to MQTT {self.mqtt_host}:{self.mqtt_port} | namespace={self.namespace} | waiting for updates..."
                )
            else:
                age = max(0.0, time.time() - self._last_snapshot_ts)
                self.info_var.set(
                    f"Connected to MQTT {self.mqtt_host}:{self.mqtt_port} | namespace={self.namespace} | last update {age:0.1f}s ago"
                )

        self.root.after(cast(Any, self.refresh_ms), self._drain_inbox)

    def _render_status(self, status_msg: dict[str, Any]) -> None:
        checkouts = status_msg.get("checkouts")

        # Clear existing rows.
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not isinstance(checkouts, dict) or not checkouts:
            # Show an explicit empty state so the UI doesn't look frozen.
            self.tree.insert("", cast(Any, tk.END), values=("(none)", "0", "0", "-"))
            return

        # Build rows
        rows: list[tuple[str, str, str, str]] = []
        now = time.time()
        for cid in sorted(checkouts.keys()):
            info = checkouts.get(cid, {})
            if not isinstance(info, dict):
                continue
            qlen = info.get("queue_len", "?")

            served_count = self._served_by_checkout.get(str(cid), 0)

            last_seen = info.get("last_seen")
            if isinstance(last_seen, (int, float)):
                age = max(0.0, now - float(last_seen))
                seen = f"{age:0.1f}s ago"
            else:
                seen = "?"
            rows.append((str(cid), str(qlen), str(served_count), seen))

        # Update tree
        for r in rows:
            self.tree.insert("", cast(Any, tk.END), values=r)


def main() -> None:
    parser = argparse.ArgumentParser(description="GUI dashboard (Tkinter + MQTT)")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--namespace", default="supermarket/v0")
    parser.add_argument("--refresh-ms", type=int, default=250)
    args = parser.parse_args()

    app = DashboardApp(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        namespace=args.namespace,
        refresh_ms=args.refresh_ms,
    )
    app.start()


if __name__ == "__main__":
    main()

