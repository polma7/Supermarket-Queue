"""MQTT topic helpers.

We keep topic construction in one place so all components agree on naming.

Topic layout (v0) under a configurable namespace (default: `supermarket/v0`):

Request/response:
- `<ns>/manager/requests`
- `<ns>/manager/responses/<client_id>`
- `<ns>/checkouts/requests`
- `<ns>/checkouts/responses/<checkout_id>`

Streaming/broadcast (normal operation):
- `<ns>/status/updates`
    Manager broadcasts periodic aggregated status snapshots.
- `<ns>/checkouts/status/<checkout_id>`
    Each checkout publishes its own status (heartbeat + local counters).

You can run multiple independent demos on a shared broker by changing the
`namespace` parameter (e.g. `--namespace demo/alice`).
"""

from __future__ import annotations


def manager_requests(namespace: str = "supermarket/v0") -> str:
    return f"{namespace}/manager/requests"


def manager_responses(client_id: str, namespace: str = "supermarket/v0") -> str:
    return f"{namespace}/manager/responses/{client_id}"


def checkout_requests(namespace: str = "supermarket/v0") -> str:
    return f"{namespace}/checkouts/requests"


def checkout_responses(checkout_id: str, namespace: str = "supermarket/v0") -> str:
    return f"{namespace}/checkouts/responses/{checkout_id}"


def status_updates(namespace: str = "supermarket/v0") -> str:
    """Broadcast aggregated status snapshots.

    In normal operation the manager publishes periodic snapshots here.
    Observers subscribe to this topic.
    """
    return f"{namespace}/status/updates"


def checkout_status(checkout_id: str, namespace: str = "supermarket/v0") -> str:
    """Per-checkout status stream.

    In normal operation each checkout publishes periodic status messages here.
    The manager (and observers) can subscribe.
    """
    return f"{namespace}/checkouts/status/{checkout_id}"
