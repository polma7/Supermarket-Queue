# Supermarket Queue Management System (MQTT)

Distributed-systems / DAI project in which supermarket checkout counters are implemented as **agents** that coordinate via an **MQTT broker**.

---

## 1) Run (single command)

### Prerequisites
- Python
- MQTT broker (Mosquitto suggested)

Install dependencies:

```bash
python -m pip install -U pip
python -m pip install paho-mqtt pytest
```

Start Mosquitto (example):

```bash
mosquitto -p 1883
```

### Run the full environment

```bash
python -m supermarket_queue.app run \
  --mqtt-host 127.0.0.1 --mqtt-port 1883 \
  --num-checkouts 5 \
  --arrival-rate 0.5 \
  --mean-basket-size 20 \
  --base-seconds 0.5 \
  --per-item-seconds 0.05 \
  --gui
```

Stop everything with **Ctrl+C** (or close the GUI window if `--gui` is enabled).

---

## 2) Environment elements (processes)

`python -m supermarket_queue.app run ...` starts:

1) **Manager** (`manager.py`)
- Stores queue state per checkout.
- Assigns arriving customers to checkouts.

2) **Checkout agents** (`checkout.py`) — **N processes**
- Checkouts `C1..CN` are agents that:
  - register to the manager
  - request customers to serve
  - simulate service time
  - publish telemetry (`served_count`)

3) **Customer generator** (`generator.py`)
- Generates customers automatically.
- Uses **Poisson arrivals** (random exponential inter-arrivals).
- Generates `basket_size` for each customer.

4) **GUI dashboard** (`gui.py`) *(optional)*
- Subscribes to manager snapshots and checkout telemetry.

---

## 3) Main parameters

These parameters are passed to `app run`.

### `--num-checkouts` (int)
Number of checkout agents started. IDs: `C1..C<num_checkouts>`.

### `--arrival-rate` (float)
Arrival rate **λ** (customers/second).
- Customers arrive as a **Poisson process**.
- Inter-arrival times are sampled from **Exponential(λ)**.

### `--mean-basket-size` (float)
Mean number of grocery items per generated customer. The generator samples an integer `basket_size` around this mean.

### `basket_size` (int)
Per-customer number of grocery items. Used for:
1) **Manager assignment**: queue workload uses basket sizes.
2) **Checkout service time**: determines the serving duration.

### `--base-seconds` (float)
Fixed overhead time per customer (e.g., paying/bagging).

### `--per-item-seconds` (float)
Additional time per grocery item.

### Service time formula
For each customer at a checkout:

```
service_time = base_seconds + per_item_seconds * basket_size
```

### `served_count` (int)
Per-checkout counter of how many customers have been served.

### `--mqtt-host`, `--mqtt-port`
MQTT broker address.

### `--namespace`
Topic prefix to isolate runs. All components must share the same namespace.

### `--gui`
Opens the Tkinter GUI dashboard.

---

## 4) Load balancing (manager decision)

Implemented in `QueueManager.assign_customer()` (`manager.py`).

### Workload model
For each checkout:

```
workload = sum(basket_size of customers in queue) + queue_len
```

The customer is assigned to the checkout with the smallest workload.

### Tie-breaking
If multiple checkouts share the same minimal workload, the manager uses **round-robin** among those tied checkouts to avoid bias toward early checkout IDs.

---

## 5) GUI fields

The GUI shows one row per checkout:
- **Checkout**: checkout id (`C1`, `C2`, ...)
- **Queue length**: customers currently waiting (from manager snapshot)
- **Served customers**: `served_count` (from checkout telemetry)
- **Last seen**: time since the last heartbeat observed by the manager

---

## 6) MQTT topics

Defined in `mqtt_topics.py`.

### Request/response (RPC-like over MQTT)
- `/<ns>/manager/requests`
- `/<ns>/manager/responses/<client_id>`
- `/<ns>/checkouts/requests`
- `/<ns>/checkouts/responses/<checkout_id>`

### Streaming telemetry
- `/<ns>/status/updates` — manager publishes periodic snapshots
- `/<ns>/checkouts/status/<checkout_id>` — checkout publishes telemetry (`served_count`, etc.)

---

## 7) Files

### `supermarket_queue/app.py`
Main CLI entrypoint.
- `run`: starts manager + N checkouts + generator; optional GUI
- advanced/debug: `manager`, `checkout`, `customer`

### `supermarket_queue/run_all.py`
Process launcher used by `app run`.

### `supermarket_queue/manager.py`
Manager agent.
- `QueueManager`: queues + assignment algorithm
- `MqttQueueManagerService`: MQTT adapter (requests + snapshots)

### `supermarket_queue/checkout.py`
Checkout agent.
- registers to manager
- requests customers (`checkout_next`)
- simulates service time
- publishes `checkout_status` with `served_count`

### `supermarket_queue/generator.py`
Customer generator.
- Poisson arrivals (`dt ~ Exp(λ)`)
- sampled `basket_size`

### `supermarket_queue/customer.py`
Manual customer client.

### `supermarket_queue/gui.py`
Tkinter dashboard.

### `supermarket_queue/mqtt_client.py`
MQTT wrapper (JSON + request/response via `corr_id` + `reply_to`).

### `supermarket_queue/mqtt_topics.py`
Topic-name helpers.

### `supermarket_queue/service_time.py`
Service-time helper function.

### `supermarket_queue/errors.py`
Shared error envelope.

---

## 8) Tests

```bash
pytest
```
