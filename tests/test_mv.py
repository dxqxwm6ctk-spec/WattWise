"""M&V: baseline model quality, honest refusal without data, savings against the meter."""

import time

import pytest

from backend import actions, config, db, mv

T0 = time.mktime((2026, 11, 1, 18, 0, 0, 0, 0, -1))   # local 18:00, site clock


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    mv._cache.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def put(conn, i, power_w, occupied=True, temp=25.0):
    """Reading i: site clock advances one minute per reading (like the x60 simulator)."""
    rooms = [{"room_id": r, "temp_c": temp, "light": 1200, "occupied": occupied if r == "living" else False,
              "window_open": False} for r in ("living", "bedroom", "kids", "kitchen", "bath", "hall")]
    actions.ingest(conn, {"site": "home", "source": "simulator", "meter_ts": T0 + i * 60,
                          "meter": {"power_w": power_w, "energy_kwh": 100.0}, "rooms": rooms})


def wobble(i):
    return (i % 7) * 10 - 30           # deterministic noise, mean ~0


def approve_now(conn):
    """Record an approved action at the current real time (end of the baseline)."""
    conn.execute("INSERT INTO approvals (site, device_id, turn_on, created_ts, expires_ts, title, reason, status, "
                 "decided_ts) VALUES ('home','bedAc',0,?,?,'t','r','approved',?)",
                 (time.time(), time.time(), time.time()))
    time.sleep(0.01)


def test_not_enough_baseline_shows_no_number(conn):
    for i in range(60):                 # 1 hour = 4 intervals < 12
        put(conn, i, 2000 + wobble(i))
    r = mv.compute(conn, "home")
    assert r["status"] == "not_enough_baseline" and "saved_kwh" not in r


def test_model_ready_but_no_action_yet(conn):
    for i in range(240):
        put(conn, i, 2000 + wobble(i))
    r = mv.compute(conn, "home")
    assert r["status"] == "no_reporting_data"
    assert r["model"]["passes"] and r["model"]["cv_rmse_pct"] < 5


def test_savings_match_a_known_drop(conn):
    for i in range(240):                # 4 h baseline at ~2000 W
        put(conn, i, 2000 + wobble(i))
    approve_now(conn)
    for i in range(240, 360):           # 2 h after the action at ~1000 W, same occupancy/temp
        put(conn, i, 1000 + wobble(i))
    r = mv.compute(conn, "home")
    assert r["status"] == "ok"
    assert r["saved_kwh"] == pytest.approx(2.0, abs=0.15)      # 1 kW x 2 h
    assert r["saved_pct"] == pytest.approx(50, abs=5)
    assert r["saved_band_kwh"] < 0.5


def test_more_consumption_is_reported_as_negative(conn):
    for i in range(240):
        put(conn, i, 2000 + wobble(i))
    approve_now(conn)
    for i in range(240, 300):
        put(conn, i, 2600 + wobble(i))
    r = mv.compute(conn, "home")
    assert r["status"] == "ok" and r["saved_kwh"] < 0


def test_noisy_baseline_is_refused(conn):
    for i in range(240):                # random-looking jumps the features cannot explain
        put(conn, i, 300 if ((i // 15) * 7919) % 3 else 4000)
    approve_now(conn)
    for i in range(240, 300):
        put(conn, i, 1000)
    r = mv.compute(conn, "home")
    assert r["status"] == "model_not_good_enough" and "saved_kwh" not in r


def test_report_page_uses_the_measured_numbers(conn):
    from backend import report
    for i in range(240):
        put(conn, i, 2000 + wobble(i))
    approve_now(conn)
    for i in range(240, 360):
        put(conn, i, 1000 + wobble(i))
    page = report.build(conn, "home")
    r = mv.compute(conn, "home")
    assert f'{r["saved_kwh"]:,.2f}' in page
    assert "بيانات تركيبية" in page and "CV(RMSE)" in page


def test_report_endpoint_without_data(conn):
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as client:
        res = client.get("/api/sites/home/report")
    assert res.status_code == 200 and "تقرير التوفير" in res.text
