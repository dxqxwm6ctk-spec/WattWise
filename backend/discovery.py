"""Help the phone app find the laptop without typing an address.

Two ways, both work with no internet (local Wi-Fi or a phone hotspot):

1. Announcement: every 2 seconds the backend sends a tiny UDP broadcast message
   {"app": "wattwise", "port": 8000} to the whole local network on port 47800.
   The phone app listens on that port; the sender's address is the laptop's address.
2. QR code: the dashboard shows a QR code that contains the server address.
   The phone app scans it with the camera.

The message carries no personal data, only the app name and the port.
"""

import json
import os
import socket
import threading

import qrcode
import qrcode.image.svg

DISCOVERY_PORT = 47800     # UDP port the phone app listens on
ANNOUNCE_EVERY_S = 2.0


def server_port() -> int:
    """The port the backend runs on (run_demo.py sets WATTWISE_PORT; 8000 by default)."""
    try:
        return int(os.environ.get("WATTWISE_PORT", "8000"))
    except ValueError:
        return 8000


def lan_ip() -> str:
    """The laptop's address on the local network (the one the phone should use)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no packet is sent; it only picks the right network card
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def server_url() -> str:
    return f"http://{lan_ip()}:{server_port()}"


def qr_svg(text: str) -> str:
    """A QR code as SVG text (pure Python, works offline)."""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    return img.to_string(encoding="unicode")


def _broadcast_targets() -> list[str]:
    """Where to send the announcement: the general broadcast address plus the
    broadcast address of every local network card (assumes a home-style /24 network)."""
    targets = {"255.255.255.255"}
    try:
        ips = {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        ips = set()
    ips.add(lan_ip())
    for ip in ips:
        if ip.startswith("127."):
            continue
        targets.add(ip.rsplit(".", 1)[0] + ".255")
    return sorted(targets)


def announcement() -> bytes:
    return json.dumps({"app": "wattwise", "port": server_port()}).encode()


class Announcer:
    """Background thread that keeps announcing the server on the local network."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wattwise-announcer", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not self._stop.is_set():
                msg = announcement()
                for target in _broadcast_targets():
                    try:
                        sock.sendto(msg, (target, DISCOVERY_PORT))
                    except OSError:
                        pass   # a network card that cannot broadcast; try the others
                self._stop.wait(ANNOUNCE_EVERY_S)
