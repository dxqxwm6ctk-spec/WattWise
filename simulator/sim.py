"""WattWise digital twin: a simulated house that talks to the backend exactly like the ESP32.

Every real second it:
  1. asks the backend for commands (relay states, AC set points, demo scenario),
  2. computes what the main meter and the room sensors would read,
  3. posts one reading to /api/readings.

All data here is SYNTHETIC. The simulator clock runs 60x faster than real time
(1 real second = 1 simulated minute) so a demo shows a whole evening quickly.

Run:  python -m simulator.sim            (backend must be running on port 8000)
      python -m simulator.sim --site building     (the 10-room office floor)
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

# Demo "unknown_load" scenario: a device the backend does not know (anomaly detection demo).
UNKNOWN_LOAD_W = 700

# True power of a newly plugged-in device, per kind (the backend never sees this;
# it has to measure the step on the meter, like with real hardware).
NEW_DEVICE_W = {"ac": 1100, "light": 30, "heater": 1800, "tv": 110, "washer": 600, "pc": 180,
                "router": 12, "fridge": 150, "medical": 80, "other": 75}

# Demo "stranger_device" scenario: a small device with no saved fingerprint (unknown-device alert).
STRANGER_W, STRANGER_PF = 60, 0.7

# Teach mode: the simulator plays the user switching the room's devices on one by one.
TEACH_FIRST_S, TEACH_GAP_S = 6, 7


# Synthetic power factor per kind (typical textbook values, NOT measured). A real
# PZEM-004T reports the PF of the whole circuit; the backend works out each
# device's PF from the jump when it switches (backend/nilm.py).
KIND_PF = {"light": 0.95, "heater": 1.0, "fan": 0.80, "ac": 0.85, "tv": 0.90, "pc": 0.95, "washer": 0.70,
           "fridge": 0.80, "router": 0.55, "other": 0.90, "fire_alarm": 0.60, "medical": 0.90,
           "ev": 0.99}


def http_json(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


class House:
    def __init__(self, site: str, speed: float, start_kwh: float):
        cfg = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))["sites"][site]
        self.site = site
        # Who is there in the evening snapshot (PIR: occupied or empty, nothing more) and base temperatures.
        self.occupied_cfg = {r["id"]: r["sim"]["occupied"] for r in cfg["rooms"]}
        self.base_temp = {r["id"]: r["sim"]["temp_c"] for r in cfg["rooms"]}
        self.demo_room = cfg.get("demo_waste", {}).get("room")
        self.devices = {d["id"]: d for d in cfg["devices"]}
        self.rooms = [r["id"] for r in cfg["rooms"]]
        self.on = {k: d.get("on", True) for k, d in self.devices.items()}
        self.setpoint = {k: d["setpoint"] for k, d in self.devices.items() if "setpoint" in d}
        self.extra_w: dict[str, float] = {}      # devices added from the app: id -> true watts
        self.extra_kind: dict[str, str] = {}     # and their kind (for the synthetic PF)
        self.plug_w: dict[str, float] = {}       # simulated WiFi smart plugs: id -> watts drawn now
        # Devices that exist in the house but the backend does not know (sites.json "sim.unlabeled").
        # They start off; in teach mode the "user" switches them on one by one.
        self.hidden = {r["id"]: r["sim"].get("unlabeled", []) for r in cfg["rooms"] if "sim" in r}
        self.hidden_on: set[tuple[str, int]] = set()
        room_ids = [r["id"] for r in cfg["rooms"]]
        self.stranger_room = next((r for r in ("kitchen", "kitchenette") if r in room_ids), room_ids[0])
        self.meter_room = None                   # teach mode: the PZEM is on this room's breaker
        self.teach_started = None
        self.teach_plan: list[tuple[float, str, int, bool]] = []   # (real time, room, index, on)
        self.speed = speed
        self.clock = datetime.now().replace(hour=19, minute=30, second=0, microsecond=0).timestamp()
        self.energy_kwh = start_kwh
        self.scenario = "normal"
        self.fault_until = 0.0
        # Home EV charger (synthetic): the car's battery, filled while the charger is on.
        self.ev_cfg = cfg.get("ev") or {}
        self.ev_soc = float(self.ev_cfg.get("sim", {}).get("start_soc", 55))
        self.ev_draw_w = 0.0

    # --- apply what the backend asked for ---
    def apply(self, cmd: dict) -> None:
        for dev_id, on in cmd["relays"].items():
            self.on[dev_id] = on
        self.setpoint.update({k: v for k, v in cmd["setpoints"].items() if v is not None})
        learning = cmd.get("learning")
        if learning and learning["device_id"] not in self.extra_w:
            base = NEW_DEVICE_W.get(learning["kind"], 75)
            self.extra_w[learning["device_id"]] = round(base * random.uniform(0.9, 1.1))
            self.extra_kind[learning["device_id"]] = learning["kind"]
        # A device being learned is switched on by the user, before it exists in the backend.
        self.learning_id = learning["device_id"] if learning else None
        # Drop loads from a cancelled "add device" flow.
        for dev_id in list(self.extra_w):
            if dev_id not in cmd["relays"] and dev_id != self.learning_id:
                del self.extra_w[dev_id]
        # Simulated smart plugs: the backend tells us what each one really draws.
        self.plug_w = cmd.get("plug_loads") or {}
        self._teach(cmd.get("room_meter"))
        if cmd["scenario"] != self.scenario:
            self.scenario = cmd["scenario"]
            if self.scenario == "sensor_fault":
                self.fault_until = time.time() + 25
            if self.scenario == "ev_arrives":   # the car comes home with a low battery
                self.ev_soc = float(self.ev_cfg.get("sim", {}).get("arrive_soc", 30))

    def _teach(self, rm: dict | None) -> None:
        """Teach mode: move the meter to the room's breaker and switch its unknown devices on one by one."""
        now = time.time()
        if not rm:
            self.meter_room, self.teach_started, self.teach_plan = None, None, []
            return
        self.meter_room = rm["room"]
        if rm["started_ts"] and rm["started_ts"] != self.teach_started:
            self.teach_started = rm["started_ts"]
            items = list(range(len(self.hidden.get(rm["room"], []))))
            self.teach_plan = [(now + 2, rm["room"], i, False) for i in items]
            self.teach_plan += [(now + TEACH_FIRST_S + TEACH_GAP_S * k, rm["room"], i, True) for k, i in enumerate(items)]
        if not rm.get("guided"):
            self.teach_plan = []
        while self.teach_plan and self.teach_plan[0][0] <= now:
            _, room, i, on = self.teach_plan.pop(0)
            (self.hidden_on.add if on else self.hidden_on.discard)((room, i))

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
            # The compressor cycles: on 15 minutes, off 10 (clean steps on the meter).
            return d["rated_w"] if minute % 25 < 15 else 0.0
        if d["kind"] == "ac":
            return d["rated_w"] * (1 + (24 - self.setpoint.get(dev_id, 24)) * 0.06)
        if d["kind"] == "ev":
            return self.ev_draw_w
        return d["rated_w"]

    def step_ev(self) -> None:
        """Charge the car: full power up to 90 %, then the car tapers the current down (like real EVs)."""
        ev_on = any(self.on.get(k) for k, d in self.devices.items() if d["kind"] == "ev")
        rated = next((d["rated_w"] for d in self.devices.values() if d["kind"] == "ev"), 0)
        if not ev_on or self.ev_soc >= 100 or not rated:
            self.ev_draw_w = 0.0
            return
        taper = 1.0 if self.ev_soc < 90 else max(0.08, (100 - self.ev_soc) / 10)
        self.ev_draw_w = rated * taper * random.uniform(0.985, 1.0)
        battery = self.ev_cfg.get("battery_kwh", 60)
        self.ev_soc = min(100.0, self.ev_soc + self.ev_draw_w / 1000 * (self.speed / 3600) / battery * 100 * 0.92)

    def occupied(self, room: str) -> bool:
        if self.scenario == "holiday":
            return False
        if self.scenario == "bedroom_empty_window" and room == self.demo_room:
            return False
        return self.occupied_cfg.get(room, False)

    def window_open(self, room: str) -> bool:
        return self.scenario == "bedroom_empty_window" and room == self.demo_room

    def temperature(self, room: str) -> float:
        t = self.base_temp.get(room, 25.0)
        if self.window_open(room):
            t += 3.3
        if self.scenario == "heat_wave":
            t += 5.0
        ac = [k for k, d in self.devices.items() if d["room"] == room and d["kind"] == "ac"]
        if ac and not any(self.on.get(k) for k in ac):
            t += 1.5
        return round(t + random.uniform(-0.15, 0.15), 1)

    def loads(self, room: str | None = None) -> list[tuple[float, float]]:
        """(watts, pf) of everything drawing power, in one room or the whole house."""
        out = []
        for k, d in self.devices.items():
            if room is None or d["room"] == room:
                out.append((self.device_w(k), KIND_PF.get(d["kind"], 0.9)))
        if room is None:
            out += [(self.device_w(k), KIND_PF.get(self.extra_kind.get(k, "other"), 0.9))
                    for k in self.extra_w if k not in self.plug_w]
            out += [(w, 0.9) for w in self.plug_w.values()]   # simulated WiFi smart plugs
        for r, items in self.hidden.items():
            if room is None or r == room:
                out += [(it["w"], it["pf"]) for i, it in enumerate(items) if (r, i) in self.hidden_on]
        if self.scenario == "stranger_device" and room in (None, self.stranger_room):
            out.append((STRANGER_W, STRANGER_PF))
        if self.scenario == "unknown_load" and room is None:   # a load the backend does not know about
            out.append((UNKNOWN_LOAD_W, 0.95))
        return out

    @staticmethod
    def total(loads: list[tuple[float, float]], noise_w: float) -> tuple[float, float | None]:
        """Total watts (with meter noise) and the power factor of the sum."""
        p = sum(w for w, _ in loads)
        q = sum(w * math.tan(math.acos(pf)) for w, pf in loads if w > 0)
        pf = round(p / math.hypot(p, q), 2) if p > 1 else None
        return max(0.0, p + random.uniform(-noise_w, noise_w)), pf

    def reading(self) -> dict:
        self.step_ev()
        power, pf = self.total(self.loads(), 20)
        minute = self.clock / 60
        volt = 229.4 + math.sin(minute) * 0.8
        self.energy_kwh += power / 1000 * (self.speed / 3600)
        return {
            "site": self.site,
            "source": "simulator",
            "meter_ts": self.clock,
            "meter": {
                "power_w": round(power, 1),
                "energy_kwh": round(self.energy_kwh, 3),
                "voltage_v": round(volt, 1),
                "current_a": round(power / volt / (pf or 0.94), 2),
                "freq_hz": round(50 + math.sin(minute * 1.7) * 0.03, 2),
                "pf": pf,
            },
            "circuit": self.circuit(),
            "rooms": [
                {"room_id": r, "temp_c": self.temperature(r), "humidity": 40,
                 "light": 300 + (900 if any(self.on.get(k) for k, d in self.devices.items()
                                         if d["room"] == r and d["kind"] == "light") else 0),
                 "occupied": self.occupied(r), "window_open": self.window_open(r)}
                for r in self.rooms
            ],
            **({"ev": {"soc_pct": round(self.ev_soc, 1), "plugged": True}} if self.ev_cfg else {}),
        }


    def circuit(self) -> dict | None:
        """Teach mode: what a PZEM on this room's breaker reads (much less noise than the whole house)."""
        if not self.meter_room:
            return None
        p, pf = self.total(self.loads(self.meter_room), 0.3)
        return {"room_id": self.meter_room, "power_w": round(p, 1), "pf": pf}


def main() -> None:
    ap = argparse.ArgumentParser(description="WattWise house simulator (synthetic data)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--site", default="home", help="simulated site from config/sites.json: home or building")
    ap.add_argument("--speed", type=float, default=60, help="simulated seconds per real second")
    ap.add_argument("--start-kwh", type=float, default=286, help="synthetic meter reading at start")
    args = ap.parse_args()

    house = House(args.site, args.speed, args.start_kwh)
    house.learning_id = None
    print(f"Simulator running: site={args.site}  {args.url}  speed x{args.speed:g}  (Ctrl+C to stop)")
    while True:
        started = time.time()
        try:
            house.apply(http_json("GET", f"{args.url}/api/sites/{args.site}/commands"))
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
