"""Record a backup video of the demo (simulator), using Playwright's browser.

Run the demo first, on a fresh database, and let it learn for ~4 minutes
(the M&V baseline needs 3 simulated hours before the first action):

    python scripts/run_demo.py --fresh
    python scripts/record_demo_video.py --wait 240

The video (.webm) is written to demo_video/. It shows: the goal, waste being
created, the approval on the phone, the meter verification, a rejection with
no action, an anomaly alert, the savings report and the 10-room building.
Needs: pip install playwright && playwright install chromium
"""

import argparse
import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def api(url: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def wait_pending(url: str, site: str = "home", seconds: int = 20) -> bool:
    for _ in range(seconds * 2):
        if api(url, f"/api/sites/{site}/state").get("pending"):
            return True
        time.sleep(0.5)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--wait", type=int, default=0, help="seconds to let the simulator learn before recording")
    ap.add_argument("--out", default=str(ROOT / "demo_video"))
    args = ap.parse_args()
    url = args.url
    if args.wait:
        print(f"Letting the simulator learn for {args.wait} s ...")
        time.sleep(args.wait)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  record_video_dir=args.out, record_video_size={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(f"{url}/index.html?site=home")
        page.wait_for_timeout(4000)

        # 1. Give the agent a goal.
        page.click('[data-act="set-goal"]')
        page.wait_for_timeout(3000)
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(2500)
        page.mouse.wheel(0, -700)

        # 2. Create waste: the bedroom is empty and its window is open, the AC is on.
        page.click('[data-act="scenario"][data-name="bedroom_empty_window"]')
        wait_pending(url)
        page.wait_for_timeout(3000)

        # 3. Approve on the phone (the phone page is shown in the frame on the left).
        phone = page.frame_locator("iframe")
        phone.locator('[data-act="approve"]').click()
        page.wait_for_timeout(9000)             # executing, then verified by the meter
        page.mouse.wheel(0, 2600)               # devices, bill (forecast + M&V), audit log
        page.wait_for_timeout(5000)
        page.mouse.wheel(0, -2600)
        page.wait_for_timeout(1500)

        # 4. Reject: holiday, everybody is out. Reject means nothing happens.
        page.select_option("#scenario-pick", "holiday")
        wait_pending(url, seconds=30)
        page.wait_for_timeout(2500)
        phone.locator('[data-act="reject"]').click()
        page.wait_for_timeout(5000)

        # 5. Anomaly: a load nobody registered.
        page.select_option("#scenario-pick", "unknown_load")
        page.wait_for_timeout(9000)
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, -900)
        page.select_option("#scenario-pick", "normal")
        page.wait_for_timeout(2000)

        # 6. The savings report.
        page.goto(f"{url}/api/sites/home/report")
        page.wait_for_timeout(3500)
        for _ in range(4):
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(1500)

        # 7. Same agent on the 10-room building.
        page.goto(f"{url}/index.html?site=building")
        page.wait_for_timeout(5000)
        page.mouse.wheel(0, 1300)
        page.wait_for_timeout(4000)

        video = page.video.path()
        ctx.close()
        browser.close()
    print("Video saved:", video)


if __name__ == "__main__":
    main()
