"""Find smart plugs on the local Wi-Fi. No internet needed.

1. Ask every address of our /24 network (for example 192.168.1.1 .. 254), in parallel,
   with a very short timeout: does port 80 or 8081 answer? If yes, is it a
   Shelly (GET /shelly), a Tasmota (GET /cm?cmnd=Status 0) or a Sonoff DIY (port 8081)?
2. TP-Link and Tuya plugs announce themselves on UDP broadcast; their libraries listen.
3. Simulated plugs are always listed (clearly labelled), so the demo works with no hardware.

We only read the plug's model and MAC, nothing about people.
"""

import os
import socket
from concurrent.futures import ThreadPoolExecutor

from backend import discovery
from backend.plugs import kasa_tapo, shelly, simulated, sonoff, tasmota, tuya

CONNECT_TIMEOUT_S = 0.3
PROBE_TIMEOUT_S = 1.5


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S):
            return True
    except OSError:
        return False


def _probe_host(host: str) -> dict | None:
    if _port_open(host, 80):
        for drv in (shelly, tasmota):
            found = drv.probe(host, PROBE_TIMEOUT_S)
            if found:
                return found
    if _port_open(host, sonoff.PORT):
        return sonoff.probe(host, PROBE_TIMEOUT_S)
    return None


def subnet_hosts() -> list[str]:
    """All addresses of our /24 network except our own. PLUG_SCAN_SUBNET=192.168.1 overrides."""
    prefix = os.environ.get("PLUG_SCAN_SUBNET", "").strip().rstrip(".")
    me = discovery.lan_ip()
    if not prefix:
        if me.startswith("127.") or me.count(".") != 3:
            return []
        prefix = me.rsplit(".", 1)[0]
    return [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" != me]


def scan(include_lan: bool = True) -> list[dict]:
    found: list[dict] = []
    if include_lan:
        with ThreadPoolExecutor(max_workers=80) as pool:
            udp = [pool.submit(kasa_tapo.scan, 3), pool.submit(tuya.scan, 3)]
            http = list(pool.map(_probe_host, subnet_hosts()))
            found += [f for f in http if f]
            for fut in udp:
                try:
                    found += fut.result(timeout=10)
                except Exception:
                    pass
    found += simulated.scan()
    # One entry per address (the HTTP probe wins over a broadcast answer).
    seen, out = set(), []
    for f in found:
        if f["host"] not in seen:
            seen.add(f["host"])
            out.append(f)
    return out
