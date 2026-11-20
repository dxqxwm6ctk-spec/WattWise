"""WattWise backend: one FastAPI server for the ESP32, the simulator, the dashboard and the phone app.

Run:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import actions, agent, assistant, bill_reader, config, connectivity, db, discovery, report, schedules, state


async def _agent_loop():
    while True:
        try:
            await asyncio.to_thread(agent.tick_all)
        except Exception as exc:  # keep the loop alive, never crash the server
            print("agent tick failed:", exc)
        await asyncio.sleep(config.AGENT_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(_agent_loop())
    announcer = discovery.Announcer()   # lets the phone app find this laptop on the Wi-Fi
    announcer.start()
    yield
    announcer.stop()
    task.cancel()


app = FastAPI(title="WattWise", lifespan=lifespan)


def _run(fn, *args, **kwargs):
    """Run an action in a DB transaction and turn ActionError into HTTP 400."""
    try:
        with db.connect() as conn:
            return fn(conn, *args, **kwargs)
    except actions.ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- request bodies ----------

class Meter(BaseModel):
    power_w: float
    energy_kwh: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    freq_hz: float | None = None
    pf: float | None = Field(default=None, ge=0, le=1)   # power factor (PZEM-004T)


class RoomReading(BaseModel):
    room_id: str
    temp_c: float | None = None
    humidity: float | None = None
    light: float | None = None
    occupied: bool | None = None
    window_open: bool | None = None


class Reading(BaseModel):
    site: str
    source: str = "device"
    meter_ts: float | None = None
    meter: Meter
    rooms: list[RoomReading] = []
    estop_pressed: bool = False
    ev: dict | None = None          # optional: what a home EV charger reports (battery %, plugged in)


class Goal(BaseModel):
    text: str = Field(max_length=500)
    bill_target_jd: float | None = Field(default=None, ge=1, le=1000)


class Toggle(BaseModel):
    on: bool
    confirmed: bool = False


class Setpoint(BaseModel):
    value: float


class Scenario(BaseModel):
    name: str


class TariffType(BaseModel):
    type: str


class LearnStart(BaseModel):
    kind: str


class NewDevice(BaseModel):
    kind: str
    room: str
    name: str = Field(default="", max_length=60)
    allow: bool = True


class Command(BaseModel):
    text: str = Field(max_length=300)


class BillPhoto(BaseModel):
    # base64 of a JPG/PNG/WEBP photo (a data: URL is fine). Used once, never saved.
    image_b64: str = Field(max_length=6_000_000)


class BillNumbers(BaseModel):
    kwh: float = Field(gt=0, le=100_000)
    days: float | None = Field(default=None, gt=0, le=120)
    amount_jod: float | None = Field(default=None, gt=0, le=100_000)


class NewSchedule(BaseModel):
    device_id: str
    on_time: str | None = None
    off_time: str | None = None


class NewTimer(BaseModel):
    device_id: str
    minutes: int
    turn_on: bool = False
    run_now: bool = False      # "run it for N minutes": on now, off after N


class Offline(BaseModel):
    offline: bool


class Enabled(BaseModel):
    enabled: bool


class HeaterHint(BaseModel):
    hint: str = Field(default="", max_length=200)


class HeaterWindows(BaseModel):
    device_id: str
    windows: list[dict] = Field(max_length=3)


# ---------- device / simulator side ----------

@app.get("/api/health")
def health():
    return {"ok": True, "app": "wattwise"}


@app.get("/api/connect")
def connect_info():
    """The address the phone app should use (also inside the QR code)."""
    return {"url": discovery.server_url()}


@app.get("/api/connect/qr.svg")
def connect_qr(path: str = ""):
    """QR with the server address. With ?path=/app.html?site=home it opens that page directly
    (the judge scans it and gets the approval page on their own phone)."""
    if path and (not path.startswith("/") or path.startswith("//") or len(path) > 200):
        raise HTTPException(status_code=400, detail="bad path")
    return Response(discovery.qr_svg(discovery.server_url() + path), media_type="image/svg+xml")


# ---------- internet (the offline demo) ----------

@app.get("/api/internet")
def get_internet():
    s = connectivity.snapshot()
    return {"online": connectivity.is_online(), "forced": s["forced_offline"], "checked": s["online"] is not None}


@app.post("/api/internet/simulate")
def post_internet_simulate(body: Offline):
    """Rehearsal switch: pretend the internet is gone. The UI labels it as simulated."""
    connectivity.set_forced_offline(body.offline)
    with db.connect() as conn:
        agent.note_internet_changes(conn)
    return {"ok": True, "online": connectivity.is_online()}


@app.post("/api/readings")
def post_reading(reading: Reading):
    _run(actions.ingest, reading.model_dump())
    return {"ok": True}


@app.get("/api/sites/{site}/commands")
def get_commands(site: str):
    return _run(actions.commands_for, site)


# ---------- dashboard / phone app ----------

@app.get("/api/sites")
def list_sites():
    return {k: {"name": v["name"], "source": v["source"]} for k, v in config.load_sites().items()}


@app.get("/api/sites/{site}/report", response_class=HTMLResponse)
def savings_report(site: str):
    """Printable savings report (M&V, verified actions, approvals, audit log)."""
    return HTMLResponse(_run(report.build, site))


@app.get("/api/sites/{site}/state")
def get_state(site: str):
    return _run(state.build, site)


@app.post("/api/sites/{site}/goal")
def post_goal(site: str, goal: Goal):
    return _run(actions.set_goal, site, goal.text, goal.bill_target_jd)


@app.post("/api/sites/{site}/approvals/{approval_id}/approve")
def post_approve(site: str, approval_id: int):
    return _run(actions.approve, site, approval_id)


@app.post("/api/sites/{site}/approvals/{approval_id}/reject")
def post_reject(site: str, approval_id: int):
    return _run(actions.reject, site, approval_id)


@app.post("/api/sites/{site}/devices/{device_id}/toggle")
def post_toggle(site: str, device_id: str, body: Toggle):
    return _run(actions.human_toggle, site, device_id, body.on, body.confirmed)


@app.post("/api/sites/{site}/devices/{device_id}/setpoint")
def post_setpoint(site: str, device_id: str, body: Setpoint):
    return _run(actions.set_setpoint, site, device_id, body.value)


@app.post("/api/sites/{site}/estop")
def post_estop(site: str):
    _run(actions.emergency_stop, site)
    return {"ok": True}


@app.post("/api/sites/{site}/reset")
def post_reset(site: str):
    _run(actions.reset_demo, site)
    return {"ok": True}


@app.post("/api/sites/{site}/scenario")
def post_scenario(site: str, body: Scenario):
    _run(actions.set_scenario, site, body.name)
    return {"ok": True}


@app.post("/api/sites/{site}/tariff")
def post_tariff(site: str, body: TariffType):
    if body.type not in config.load_tariff()["types"]:
        raise HTTPException(status_code=400, detail="نوع اشتراك مش معروف.")
    with db.connect() as conn:
        db.set_state(conn, f"tariff_type:{site}", body.type)
    return {"ok": True}


@app.post("/api/sites/{site}/learn")
def post_learn(site: str, body: LearnStart):
    return _run(actions.start_learning, site, body.kind)


@app.delete("/api/sites/{site}/learn")
def delete_learn(site: str):
    _run(actions.cancel_learning, site)
    return {"ok": True}


@app.post("/api/sites/{site}/devices")
def post_device(site: str, body: NewDevice):
    return _run(actions.add_device, site, body.room, body.name, body.kind, body.allow)


# ---------- talking to the agent (commands, analysis, report) ----------

@app.post("/api/sites/{site}/command/parse")
def post_command_parse(site: str, body: Command):
    """Understand the order and show what would happen. Changes nothing."""
    return _run(assistant.parse_command, site, body.text)


@app.post("/api/sites/{site}/command/run")
def post_command_run(site: str, body: Command):
    """The human confirmed: parse again on the server and run only the allowed items."""
    return _run(assistant.run_command, site, body.text)


@app.get("/api/sites/{site}/why")
def get_why(site: str):
    return _run(assistant.why_bill, site)


@app.get("/api/bill/status")
def get_bill_status():
    """Can the server read bill photos now (is there an API key)? If not, the apps show the manual form."""
    with db.connect() as conn:
        return bill_reader.status(conn)


@app.post("/api/sites/{site}/bill/photo")
def post_bill_photo(site: str, body: BillPhoto):
    """Claude reads the bill photo; the code checks it against the tariff and the meter. Photo is not stored."""
    return _run(bill_reader.from_photo, site, body.image_b64)


@app.post("/api/sites/{site}/bill/manual")
def post_bill_manual(site: str, body: BillNumbers):
    """Same analysis from numbers typed by hand (works with no key and no internet)."""
    return _run(bill_reader.from_manual, site, body.kwh, body.days, body.amount_jod)


@app.get("/api/sites/{site}/weekly.txt", response_class=PlainTextResponse)
def get_weekly(site: str):
    text = _run(assistant.weekly_report, site)
    return PlainTextResponse(text, headers={
        "Content-Disposition": f'attachment; filename="wattwise-weekly-{site}.txt"'})


# ---------- timers and schedules (on/off only) ----------

@app.get("/api/sites/{site}/schedules")
def get_schedules(site: str):
    return _run(schedules.listing, site)


@app.post("/api/sites/{site}/schedules")
def post_schedule(site: str, body: NewSchedule):
    return _run(schedules.add_schedule, site, body.device_id, body.on_time, body.off_time)


@app.post("/api/sites/{site}/schedules/{schedule_id}/enabled")
def post_schedule_enabled(site: str, schedule_id: int, body: Enabled):
    _run(schedules.set_enabled, site, schedule_id, body.enabled)
    return {"ok": True}


@app.delete("/api/sites/{site}/schedules/{schedule_id}")
def delete_schedule(site: str, schedule_id: int):
    _run(schedules.delete_schedule, site, schedule_id)
    return {"ok": True}


@app.post("/api/sites/{site}/timers")
def post_timer(site: str, body: NewTimer):
    return _run(schedules.add_timer, site, body.device_id, body.minutes, body.turn_on, body.run_now)


@app.delete("/api/sites/{site}/timers/{timer_id}")
def delete_timer(site: str, timer_id: int):
    _run(schedules.delete_timer, site, timer_id)
    return {"ok": True}


@app.post("/api/sites/{site}/heater/suggest")
def post_heater_suggest(site: str, body: HeaterHint):
    """A proposal only. Nothing is saved until the human confirms with /heater/apply."""
    return _run(schedules.suggest_heater, site, body.hint)


@app.post("/api/sites/{site}/heater/apply")
def post_heater_apply(site: str, body: HeaterWindows):
    return _run(schedules.apply_heater, site, body.device_id, body.windows)


# ---------- web pages ----------

@app.get("/")
def root():
    return RedirectResponse("/index.html")


app.mount("/", StaticFiles(directory=config.ROOT / "frontend"), name="frontend")
