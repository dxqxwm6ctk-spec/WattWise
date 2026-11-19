"""WattWise digital twin: a simulated house that talks to the backend exactly like the ESP32.

Every real second it:
  1. asks the backend for commands (relay states, AC set points, demo scenario),
  2. computes what the main meter and the room sensors would read,
  3. posts one reading to /api/readings.

All data here is SYNTHETIC. The simulator clock runs 60x faster than real time
(1 real second = 1 simulated minute) so a demo shows a whole evening quickly.

Run:  python -m simulator.sim            (backend must be running on port 8000)
      python -m simulator.sim --url http://192.168.1.10:8000 --speed 60
"""

import argparse
import json
import math
import random
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "home"

# Demo "unknown_load" scenario: a device the backend does not know (anomaly detection demo).
UNKNOWN_LOAD_W = 700

# True power of a newly plugged-in device, per kind (the backend never sees this;
# it has to measure the step on the meter, like with real hardware).
NEW_DEVICE_W = {"ac": 1100, "light": 30, "heater": 1800, "tv": 110, "washer": 600, "pc": 180,
                "router": 12, "fridge": 150, "medical": 80, "other": 75}

# Who is home in the evening snapshot (PIR: occupied or empty, nothing more).
OCCUPIED = {"living": True, "bedroom": True, "kids": True, "kitchen": True, "bath": False, "hall": False}
BASE_TEMP = {"living": 24.5, "bedroom": 23.8, "kids": 25.2, "kitchen": 26.0, "bath": 24.0, "hall": 24.6}


def http_json(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


class House:
    def __init__(self, speed: float, start_kwh: float):
        cfg = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))["sites"][SITE]
        self.devices = {d["id"]: d for d in cfg["devices"]}
        self.rooms = [r["id"] for r in cfg["rooms"]]
        self.on = {k: d.get("on", True) for k, d in self.devices.items()}
        self.setpoint = {k: d["setpoint"] for k, d in self.devices.items() if "setpoint" in d}
        self.extra_w: dict[str, float] = {}      # devices added from the app: id -> true watts
        self.speed = speed
        self.clock = datetime.now().replace(hour=19, minute=30, second=0, microsecond=0).timestamp()
        self.energy_kwh = start_kwh
        self.scenario = "normal"
        self.fault_until = 0.0

    # --- apply what the backend asked for ---
    def apply(self, cmd: dict) -> None:
        for dev_id, on in cmd["relays"].items():
            self.on[dev_id] = on
        self.setpoint.update({k: v for k, v in cmd["setpoints"].items() if v is not None})
        learning = cmd.get("learning")
        if learning and learning["device_id"] not in self.extra_w:
            base = NEW_DEVICE_W.get(learning["kind"], 75)
            self.extra_w[learning["device_id"]] = round(base * random.uniform(0.9, 1.1))
        # A device being learned is switched on by the user, before it exists in the backend.
        self.learning_id = learning["device_id"] if learning else None
        # Drop loads from a cancelled "add device" flow.
        for dev_id in list(self.extra_w):
            if dev_id not in cmd["relays"] and dev_id != self.learning_id:
                del self.extra_w[dev_id]
        if cmd["scenario"] != self.scenario:
            self.scenario = cmd["scenario"]
            if self.scenario == "sensor_fault":
                self.fault_until = time.time() + 25

    # --- physics (simple on purpose) ---
    def device_w(self, dev_id: str) -> float:
        if dev_id in self.extra_w:
            on = self.on.get(dev_id, False) or dev_id == self.learning_id
            return self.extra_w[dev_id] if on else 0.0
        d = self.devices[dev_id]
        if not self.on.get(dev_id):
            return 0.0
        minute = self.clock / 60
        if d["kind"] == "fridge":
            return d["rated_w"] * (0.6 + 0.4 * math.sin(minute / 3))
        if d["kind"] == "ac":
            return d["rated_w"] * (1 + (24 - self.setpoint.get(dev_id, 24)) * 0.06)
        return d["rated_w"]

    def occupied(self, room: str) -> bool:
        if self.scenario == "holiday":
            return False
        if self.scenario == "bedroom_empty_window" and room == "bedroom":
            return False
        return OCCUPIED.get(room, False)

    def window_open(self, room: str) -> bool:
        return self.scenario == "bedroom_empty_window" and room == "bedroom"

    def temperature(self, room: str) -> float:
        t = BASE_TEMP.get(room, 25.0)
        if self.window_open(room):
            t += 3.3
        if self.scenario == "heat_wave":
            t += 5.0
        ac = [k for k, d in self.devices.items() if d["room"] == room and d["kind"] == "ac"]
        if ac and not any(self.on.get(k) for k in ac):
            t += 1.5
        return round(t + random.uniform(-0.15, 0.15), 1)

    def reading(self) -> dict:
        all_ids = list(self.devices) + list(self.extra_w)
        power = sum(self.device_w(k) for k in all_ids) + random.uniform(-20, 20)
        if self.scenario == "unknown_load":   # a load the backend does not know about
            power += UNKNOWN_LOAD_W
        power = max(0.0, power)
        minute = self.clock / 60
        volt = 229.4 + math.sin(minute) * 0.8
        self.energy_kwh += power / 1000 * (self.speed / 3600)
        return {
            "site": SITE,
            "source": "simulator",
            "meter_ts": self.clock,
            "meter": {
                "power_w": round(power, 1),
                "energy_kwh": round(self.energy_kwh, 3),
                "voltage_v": round(volt, 1),
                "current_a": round(power / volt / 0.94, 2),
                "freq_hz": round(50 + math.sin(minute * 1.7) * 0.03, 2),
            },
            "rooms": [
                {"room_id": r, "temp_c": self.temperature(r), "humidity": 40,
                 "light": 300 + (900 if any(self.on.get(k) for k, d in self.devices.items()
                                         if d["room"] == r and d["kind"] == "light") else 0),
                 "occupied": self.occupied(r), "window_open": self.window_open(r)}
                for r in self.rooms
            ],
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="WattWise house simulator (synthetic data)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--speed", type=float, default=60, help="simulated seconds per real second")
    ap.add_argument("--start-kwh", type=float, default=286, help="synthetic meter reading at start")
    args = ap.parse_args()

    house = House(args.speed, args.start_kwh)
    house.learning_id = None
    print(f"Simulator running: {args.url}  speed x{args.speed:g}  (Ctrl+C to stop)")
    while True:
        started = time.time()
        try:
            house.apply(http_json("GET", f"{args.url}/api/sites/{SITE}/commands"))
            reading = house.reading()
            if time.time() >= house.fault_until:
                http_json("POST", f"{args.url}/api/readings", reading)
            print(f"\r{datetime.fromtimestamp(house.clock):%H:%M}  {reading['meter']['power_w']:7.1f} W  "
                  f"scenario={house.scenario:22}", end="", flush=True)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            print(f"\nbackend not reachable ({exc}); retrying...")
        house.clock += args.speed
        time.sleep(max(0.0, 1.0 - (time.time() - started)))


if __name__ == "__main__":
    main()
