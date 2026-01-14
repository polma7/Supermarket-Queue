from __future__ import annotations

# Single-entrypoint runner.
#
# CLEAN CLI (v0):
# - Primary way to run the project is the single command:
#     python -m supermarket_queue.app run --num-checkouts N --arrival-rate LAMBDA [--gui]
#
# We keep a few advanced subcommands for debugging and development, but the
# recommended path is `run`.

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Supermarket Queue System (MQTT) - main entrypoint")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_mqtt_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--mqtt-host", default="127.0.0.1")
        p.add_argument("--mqtt-port", type=int, default=1883)
        p.add_argument("--namespace", default="supermarket/v0")

    # ---- Normal operation: one command ----
    p_run = sub.add_parser("run", help="Start manager + N checkouts + generator (optional GUI)")
    add_mqtt_args(p_run)
    p_run.add_argument("--num-checkouts", type=int, required=True)
    p_run.add_argument("--arrival-rate", type=float, required=True, help="λ customers/second")
    p_run.add_argument("--seed", type=int, default=None)
    p_run.add_argument("--mean-basket-size", type=float, default=20.0)
    p_run.add_argument("--base-seconds", type=float, default=0.5)
    p_run.add_argument("--per-item-seconds", type=float, default=0.05)
    p_run.add_argument("--gui", action="store_true", help="open Tkinter dashboard")

    # ---- Advanced/debug subcommands (kept minimal) ----
    p_mgr = sub.add_parser("manager", help="(advanced) Start the queue manager only")
    add_mqtt_args(p_mgr)

    p_chk = sub.add_parser("checkout", help="(advanced) Start a single checkout agent")
    add_mqtt_args(p_chk)
    p_chk.add_argument("--checkout-id", required=True)
    p_chk.add_argument("--service-seconds", type=float, default=2.0)

    p_cust = sub.add_parser("customer", help="(advanced) Send one customer join request")
    add_mqtt_args(p_cust)
    p_cust.add_argument("--name", required=True)
    p_cust.add_argument("--basket-size", type=int, default=0)

    args = parser.parse_args()

    if args.cmd == "run":
        from .run_all import main as run

        run_args = [
            "--mqtt-host",
            args.mqtt_host,
            "--mqtt-port",
            str(args.mqtt_port),
            "--namespace",
            args.namespace,
            "--num-checkouts",
            str(args.num_checkouts),
            "--arrival-rate",
            str(args.arrival_rate),
            "--mean-basket-size",
            str(args.mean_basket_size),
            "--base-seconds",
            str(args.base_seconds),
            "--per-item-seconds",
            str(args.per_item_seconds),
        ]
        if args.seed is not None:
            run_args += ["--seed", str(args.seed)]
        if args.gui:
            run_args += ["--gui"]

        _dispatch_to_module_main(run, run_args)
        return

    if args.cmd == "manager":
        from .manager import main as run

        run_args = ["--mqtt-host", args.mqtt_host, "--mqtt-port", str(args.mqtt_port), "--namespace", args.namespace]
        _dispatch_to_module_main(run, run_args)
        return

    if args.cmd == "checkout":
        from .checkout import main as run

        run_args = [
            "--checkout-id",
            args.checkout_id,
            "--mqtt-host",
            args.mqtt_host,
            "--mqtt-port",
            str(args.mqtt_port),
            "--namespace",
            args.namespace,
            "--service-seconds",
            str(args.service_seconds),
        ]
        _dispatch_to_module_main(run, run_args)
        return

    if args.cmd == "customer":
        from .customer import main as run

        run_args = [
            "--name",
            args.name,
            "--basket-size",
            str(args.basket_size),
            "--mqtt-host",
            args.mqtt_host,
            "--mqtt-port",
            str(args.mqtt_port),
            "--namespace",
            args.namespace,
        ]
        _dispatch_to_module_main(run, run_args)
        return


def _dispatch_to_module_main(module_main, argv: list[str]) -> None:
    import sys

    old_argv = sys.argv[:]
    try:
        sys.argv = [old_argv[0], *argv]
        module_main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()

