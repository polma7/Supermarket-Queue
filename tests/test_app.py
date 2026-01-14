import subprocess
import sys


def test_app_help_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "supermarket_queue.app", "-h"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "main entrypoint" in out
    assert "run" in out
    assert "customer" in out


def test_run_help_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "supermarket_queue.app", "run", "-h"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "num-checkouts" in out
    assert "arrival-rate" in out
    assert "--gui" in out
