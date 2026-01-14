# Supermarket Queue Management System (MQTT)

A small distributed-systems / DAI project where supermarket checkouts are implemented as **agents** that coordinate via an **MQTT broker**.

This README is intentionally **straightforward**: it explains how to run the project, what each file does, and what the main environment variables/parameters mean.

---

## 1) What you run (one command)

### Prerequisites
- Python
- An MQTT broker (Mosquitto suggested)

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

When you run `python -m supermarket_queue.app run ...`, the launcher starts these processes:

1) **Manager** (`manager.py`)
- Stores the official state of queues for each checkout.
- Decides where each arriving customer should go.

2) **Checkout agents** (`checkout.py`) — **N processes**
- Each checkout `C1..CN` is an agent that:
  - registers to the manager
  - requests customers to serve
  - simulates service time
  - publishes telemetry (served customers)

3) **Customer generator** (`generator.py`)
- Generates customers automatically.
- Uses **Poisson arrivals** (random exponential inter-arrivals).
- Generates `basket_size` for each customer.

4) **GUI dashboard** (`gui.py`) *(optional)*
- Visual dashboard.
- Subscribes to manager snapshots + checkout telemetry.

---

## 3) Main parameters (“environment variables”) explained

These are the main knobs you set when running `app run`.

### `--num-checkouts` (int)
- How many checkout agents are started.
- They are named `C1, C2, ..., C<num_checkouts>`.

### `--arrival-rate` (float)
- This is **λ** (lambda) in customers/second.
- Customers arrive as a **Poisson process**.
- Equivalent meaning: inter-arrival times are sampled from **Exponential(λ)**.
  - Larger λ ⇒ customers arrive more frequently.

### `--mean-basket-size` (float)
- Controls the *average* number of grocery items per customer.
- The generator samples an integer `basket_size` around this mean.

### `basket_size` (int)
- A per-customer value: number of grocery items.
- Used in two places:
  1) **Manager assignment** (load balancing): queue "workload" uses basket sizes.
  2) **Checkout service time**: more items ⇒ the checkout sleeps longer.

### `--base-seconds` (float)
- Fixed overhead time added for every customer (paying, bagging, etc.).

### `--per-item-seconds` (float)
- Additional time per grocery item.

### Checkout service time formula
Each checkout uses:

```
service_time = base_seconds + per_item_seconds * basket_size
```

### `served_count` (int)
- A per-checkout counter.
- How many customers that checkout has finished serving so far.
- Published by each checkout on its status topic.

### `--mqtt-host`, `--mqtt-port`
- Broker address.

### `--namespace`
- A topic prefix to isolate multiple runs.
- If namespace differs, components won’t see each other.

### `--gui`
- Opens the GUI dashboard.

---

## 4) How decisions are made (load balancing)

The manager assigns customers to checkouts in `QueueManager.assign_customer()` (in `manager.py`).

### Workload model
For each checkout, it computes:

```
workload = sum(basket_size of customers in that checkout queue) + queue_len
```

Then it assigns the customer to the checkout with the smallest workload.

### Tie-breaking
If multiple checkouts have the same minimal workload, the manager uses **round-robin** among the tied checkouts.
This prevents systematic bias toward the first checkout IDs.

---

## 5) What the GUI shows

The GUI shows one row per checkout:
- **Checkout**: checkout id (C1, C2, ...)
- **Queue length**: how many customers are currently waiting (from manager snapshot)
- **Served customers**: `served_count` (telemetry published by the checkout)
- **Last seen**: time since the manager last received a heartbeat from that checkout

---

## 6) MQTT topics (the communication channels)

The topic structure is defined in `mqtt_topics.py`.

### Request/response (RPC-like over MQTT)
Used for registration, join requests, and “next customer” requests.

- `/<ns>/manager/requests`
- `/<ns>/manager/responses/<client_id>`
- `/<ns>/checkouts/requests`
- `/<ns>/checkouts/responses/<checkout_id>`

### Streaming telemetry
- `/<ns>/status/updates` — manager publishes periodic snapshots (queue lengths + last seen)
- `/<ns>/checkouts/status/<checkout_id>` — each checkout publishes `served_count` (and other telemetry fields)

---

## 7) File-by-file: what each file does

### `supermarket_queue/app.py`
Main CLI entrypoint.
- `run`: starts the whole environment (manager + N checkouts + generator; optional GUI)
- also includes minimal advanced subcommands: `manager`, `checkout`, `customer`

### `supermarket_queue/run_all.py`
The “launcher” logic used by `app run`.
- Spawns the manager, checkouts, generator
- Optionally starts the GUI

### `supermarket_queue/manager.py`
The manager agent.
- `QueueManager`: in-memory queues and assignment algorithm
- `MqttQueueManagerService`: MQTT adapter that receives requests and publishes snapshots

### `supermarket_queue/checkout.py`
Checkout agent.
- Registers to manager
- Requests next customer
- Simulates service time
- Publishes `checkout_status` messages with `served_count`

### `supermarket_queue/generator.py`
Arrival process / simulation.
- Poisson arrivals (`dt ~ Exp(λ)`)
- Creates customers with random `basket_size`

### `supermarket_queue/customer.py`
Manual ad-hoc client.
- Sends one `join_queue` request with optional `basket_size`

### `supermarket_queue/gui.py`
Tkinter GUI dashboard.
- Subscribes to manager snapshots and checkout telemetry

### `supermarket_queue/mqtt_client.py`
MQTT wrapper.
- JSON publish/subscribe
- `request()` helper for request/response pattern (corr_id + reply_to)

### `supermarket_queue/mqtt_topics.py`
Central place for MQTT topic names.

### `supermarket_queue/service_time.py`
The service time function:
- `compute_service_time_seconds()`

### `supermarket_queue/errors.py`
Small helper for structured error responses.

---

## 8) Quick test

```bash
pytest
```
