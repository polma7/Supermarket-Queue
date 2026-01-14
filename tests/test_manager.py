from supermarket_queue.manager import QueueManager


def test_assign_breaks_ties_round_robin():
    m = QueueManager()
    m.register_checkout("C1", 2.0)
    m.register_checkout("C2", 2.0)
    m.register_checkout("C3", 2.0)

    # To test tie-breaking, we must keep all workloads equal at each decision.
    # We simulate "instant service" by popping immediately after assignment.
    order = []
    for i in range(6):
        cid, _pos = m.assign_customer({"name": f"n{i}", "basket_size": 0})
        order.append(cid)
        assert m.next_customer(cid) is not None

    assert order[:3] == ["C1", "C2", "C3"]
    assert order[3:] == ["C1", "C2", "C3"]


def test_assign_prefers_lower_workload_then_round_robin():
    m = QueueManager()
    m.register_checkout("C1", 2.0)
    m.register_checkout("C2", 2.0)

    # First goes to C1 (tie -> RR starts at C1)
    cid1, _ = m.assign_customer({"name": "Alice", "basket_size": 10})
    assert cid1 == "C1"

    # Next should go to C2 (lower workload)
    cid2, pos2 = m.assign_customer({"name": "Bob", "basket_size": 1})
    assert cid2 == "C2"
    assert pos2 == 1
