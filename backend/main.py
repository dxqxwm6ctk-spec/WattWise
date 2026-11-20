"""WattWise backend: one FastAPI server for the ESP32, the simulator, the dashboard and the phone app.

Run:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import actions, agent, config, db, discovery, report, state


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


# ---------- device / simulator side ----------

@app.get("/api/health")
def health():
    return {"ok": True, "app": "wattwise"}


@app.get("/api/connect")
def connect_info():
    """The address the phone app should use (also inside the QR code)."""
    return {"url": discovery.server_url()}


@app.get("/api/connect/qr.svg")
def connect_qr():
    return Response(discovery.qr_svg(discovery.server_url()), media_type="image/svg+xml")


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


# ---------- web pages ----------

@app.get("/")
def root():
    return RedirectResponse("/index.html")


app.mount("/", StaticFiles(directory=config.ROOT / "frontend"), name="frontend")
