from supermarket_queue.mqtt_topics import (
    checkout_requests,
    checkout_responses,
    checkout_status,
    manager_requests,
    manager_responses,
    status_updates,
)


def test_topic_helpers():
    ns = "demo/v0"
    assert manager_requests(ns) == "demo/v0/manager/requests"
    assert manager_responses("c1", ns) == "demo/v0/manager/responses/c1"
    assert checkout_requests(ns) == "demo/v0/checkouts/requests"
    assert checkout_responses("C1", ns) == "demo/v0/checkouts/responses/C1"
    assert status_updates(ns) == "demo/v0/status/updates"
    assert checkout_status("C1", ns) == "demo/v0/checkouts/status/C1"
