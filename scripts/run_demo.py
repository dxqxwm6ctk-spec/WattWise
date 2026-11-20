"""Start the whole WattWise demo with one command (Windows, macOS, Linux).

    python scripts/run_demo.py            # backend + simulated house + 10-room building
    python scripts/run_demo.py --fresh    # same, on a new empty database (clean demo)
    python scripts/run_demo.py --no-building

It starts:
  1. the backend on port 8000 (also serves the dashboard and the phone page),
  2. the house simulator, and (unless --no-building) the building simulator.
Then it prints the addresses to open on the laptop and on the phone.
No internet is needed: everything runs on the laptop and the local Wi-Fi / hotspot.
Press Ctrl+C to stop everything.
"""

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def lan_ip() -> str:
    """The laptop's address on the local network (what the phone should open)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no packet is sent; it only picks the right network card
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def wait_for_backend(port: int, seconds: int = 30) -> bool:
    for _ in range(seconds * 2):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Start the WattWise demo")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--fresh", action="store_true", help="start on a new empty database (demo.db)")
    ap.add_argument("--no-building", action="store_true", help="do not start the 10-room building simulator")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.fresh:
        db = ROOT / "demo.db"
        for f in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
            if f.exists():
                f.unlink()
        env["WATTWISE_DB"] = str(db)

    env["WATTWISE_PORT"] = str(args.port)   # the backend announces this port to the phone app
    py = sys.executable
    procs = [subprocess.Popen([py, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", str(args.port),
                               "--log-level", "warning"], cwd=ROOT, env=env)]
    try:
        if not wait_for_backend(args.port):
            print("The backend did not start. Read the error above (is port 8000 already used?).")
            return
        url = f"http://127.0.0.1:{args.port}"
        quiet = subprocess.DEVNULL
        procs.append(subprocess.Popen([py, "-m", "simulator.sim", "--url", url], cwd=ROOT, env=env, stdout=quiet))
        if not args.no_building:
            procs.append(subprocess.Popen([py, "-m", "simulator.sim", "--site", "building", "--url", url],
                                          cwd=ROOT, env=env, stdout=quiet))
        ip = lan_ip()
        print("\nWattWise demo is running (synthetic data from the simulator).")
        print(f"  Dashboard (laptop):     {url}/index.html")
        if not args.no_building:
            print(f"  Building, 10 rooms:     {url}/index.html?site=building")
        print(f"  Phone (same Wi-Fi):     http://{ip}:{args.port}/app.html")
        print(f"  Flutter app server:     http://{ip}:{args.port}")
        print(f"  Savings report:         {url}/api/sites/home/report")
        print("Press Ctrl+C to stop.\n")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("A part of the demo stopped. Read the error above.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(procs):
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("Stopped.")


if __name__ == "__main__":
    main()
