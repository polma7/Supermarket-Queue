from __future__ import annotations

# Single-command runner.
#
# This module starts a full local system from one command by spawning child
# processes:
# - manager
# - N checkouts
# - generator (Poisson arrivals)
#
# Optionally, it can also open the Tkinter GUI dashboard in the parent process
# (use `--gui`).
#
# The core system components remain independent processes.

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class Child:
    name: str
    proc: subprocess.Popen


def run_all(
    *,
    mqtt_host: str,
    mqtt_port: int,
    namespace: str,
    num_checkouts: int,
    arrival_rate: float,
    seed: int | None,
    mean_basket_size: float,
    base_seconds: float,
    per_item_seconds: float,
    show_gui: bool,
) -> None:
    if num_checkouts <= 0:
        raise ValueError("num_checkouts must be > 0")
    if arrival_rate <= 0:
        raise ValueError("arrival_rate must be > 0")

    python = sys.executable

    # Put all children in the same process group so Ctrl+C can stop everything.
    def popen(name: str, args: list[str]) -> Child:
        proc = subprocess.Popen(
            args,
            preexec_fn=os.setsid,
        )
        return Child(name=name, proc=proc)

    children: list[Child] = []

    mgr_args = [
        python,
        "-m",
        "supermarket_queue.manager",
        "--mqtt-host",
        mqtt_host,
        "--mqtt-port",
        str(mqtt_port),
        "--namespace",
        namespace,
    ]

    children.append(popen("manager", mgr_args))

    # Small delay so the manager connects before others start spamming requests.
    time.sleep(0.5)

    for i in range(1, num_checkouts + 1):
        cid = f"C{i}"
        chk_args = [
            python,
            "-m",
            "supermarket_queue.checkout",
            "--checkout-id",
            cid,
            "--mqtt-host",
            mqtt_host,
            "--mqtt-port",
            str(mqtt_port),
            "--namespace",
            namespace,
            "--base-seconds",
            str(base_seconds),
            "--per-item-seconds",
            str(per_item_seconds),
        ]
        children.append(popen(f"checkout-{cid}", chk_args))

    # (Cleaned) We no longer spawn the separate CLI observer process.
    # The GUI (when enabled) is the primary dashboard.

    gen_args = [
        python,
        "-m",
        "supermarket_queue.generator",
        "--mqtt-host",
        mqtt_host,
        "--mqtt-port",
        str(mqtt_port),
        "--namespace",
        namespace,
        "--rate",
        str(arrival_rate),
        "--mean-basket-size",
        str(mean_basket_size),
    ]
    if seed is not None:
        gen_args += ["--seed", str(seed)]

    children.append(popen("generator", gen_args))

    print(
        "[run] started: "
        + ", ".join(f"{c.name}(pid={c.proc.pid})" for c in children)
        + "\nPress Ctrl+C to stop all."
    )

    # If GUI requested, run it in this (parent) process.
    if show_gui:
        try:
            from .gui import DashboardApp

            app = DashboardApp(mqtt_host=mqtt_host, mqtt_port=mqtt_port, namespace=namespace)
            app.start()
        finally:
            _terminate_children(children)
        return

    # Otherwise, just wait for children.
    try:
        # Wait until any child exits unexpectedly.
        while True:
            for c in children:
                rc = c.proc.poll()
                if rc is not None:
                    raise RuntimeError(f"Child {c.name} exited with code {rc}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        _terminate_children(children)


def _terminate_children(children: list[Child]) -> None:
    # Try graceful termination.
    for c in children:
        if c.proc.poll() is None:
            try:
                os.killpg(os.getpgid(c.proc.pid), signal.SIGTERM)
            except Exception:
                pass

    # Wait a bit.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if all(c.proc.poll() is not None for c in children):
            return
        time.sleep(0.1)

    # Force kill.
    for c in children:
        if c.proc.poll() is None:
            try:
                os.killpg(os.getpgid(c.proc.pid), signal.SIGKILL)
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run manager + checkouts + generator")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--namespace", default=f"supermarket/run/{int(time.time())}")
    parser.add_argument("--num-checkouts", type=int, required=True)
    parser.add_argument("--arrival-rate", type=float, required=True, help="λ customers/second")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--mean-basket-size", type=float, default=20.0)
    parser.add_argument("--base-seconds", type=float, default=0.5)
    parser.add_argument("--per-item-seconds", type=float, default=0.05)
    parser.add_argument("--gui", action="store_true", help="show Tkinter GUI dashboard")
    args = parser.parse_args()

    run_all(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        namespace=args.namespace,
        num_checkouts=args.num_checkouts,
        arrival_rate=args.arrival_rate,
        seed=args.seed,
        mean_basket_size=args.mean_basket_size,
        base_seconds=args.base_seconds,
        per_item_seconds=args.per_item_seconds,
        show_gui=args.gui,
    )


if __name__ == "__main__":
    main()

