"""Start WattWise on a cloud host such as Railway (an OPTIONAL online copy).

The competition demo does NOT need this: locally, use scripts/run_demo.py,
which works with no internet. This script is only for the hosted copy.

What it does:
  1. starts the backend on 0.0.0.0 and on the port the host gives us ($PORT),
  2. waits until /api/health answers,
  3. starts the house simulator (and the 10-room building simulator) so the
     hosted dashboard has live SYNTHETIC data.

Settings (environment variables, all optional):
  PORT              port to listen on (Railway sets it; default 8000)
  WATTWISE_DB       database file, for example /data/wattwise.db on a Railway volume
  RUN_SIMULATOR     1 = start the simulators (default), 0 = backend only
  SIM_SITES         which simulated sites to run, default "home,building"

Run locally to test:  python scripts/cloud_start.py
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def wait_for_backend(port: int, seconds: int = 60) -> bool:
    for _ in range(seconds * 2):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> int:
    port = int(os.environ.get("PORT", "8000"))
    run_sim = os.environ.get("RUN_SIMULATOR", "1") != "0"
    sites = [s.strip() for s in os.environ.get("SIM_SITES", "home,building").split(",") if s.strip()]
    py = sys.executable

    procs = [subprocess.Popen([py, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0",
                               "--port", str(port), "--log-level", "warning"], cwd=ROOT)]
    try:
        if not wait_for_backend(port):
            print("The backend did not start. Read the error above.", flush=True)
            return 1
        print(f"WattWise backend is running on port {port}.", flush=True)
        if run_sim:
            url = f"http://127.0.0.1:{port}"
            for site in sites:
                procs.append(subprocess.Popen([py, "-m", "simulator.sim", "--site", site, "--url", url],
                                              cwd=ROOT, stdout=subprocess.DEVNULL))
            print("Simulators running (synthetic data):", ", ".join(sites), flush=True)
        # If any part stops, stop everything so the host restarts the service cleanly.
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("A part of WattWise stopped. Read the error above.", flush=True)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in reversed(procs):
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
