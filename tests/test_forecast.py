"""Load forecast: persistence when there is no history, daily profile blend, honest accuracy."""

import time

import pytest

from backend import actions, config, db, forecast
from tests.test_flow import reading

# A fixed local midnight as the start of the synthetic history.
DAY0 = time.mktime((2026, 11, 1, 0, 0, 0, 0, 0, -1))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    forecast._cache.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def put(conn, meter_ts, power_w):
    r = reading(power_w)
    r["meter_ts"] = meter_ts
    actions.ingest(conn, r)


def test_no_history_means_now(conn):
    for i in range(10):
        put(conn, DAY0 + 20 * 3600 + i * 60, 1500)
    f = forecast.forecast(conn, "home")
    assert all(s["method"] == "now" and s["power_w"] == 1500 for s in f["steps"])
    assert f["kwh"] == pytest.approx(9.0)          # 6 hours x 1.5 kW


def test_profile_is_blended_and_dominates_later_hours(conn):
    # Yesterday: 1000 W from 20:00 to 01:59.
    for h in range(20, 26):
        for m in range(0, 60, 2):
            put(conn, DAY0 + h * 3600 + m * 60, 1000)
    # Today at 20:xx the house draws 3000 W.
    for i in range(5):
        put(conn, DAY0 + 86400 + 20 * 3600 + i * 60, 3000)
    steps = forecast.forecast(conn, "home")["steps"]
    assert steps[0]["hour"] == "20:00" and steps[0]["method"] == "profile+now"
    assert steps[0]["power_w"] == 2000            # 0.5 * 3000 + 0.5 * 1000
    assert steps[1]["power_w"] == 1500            # 0.25 * 3000 + 0.75 * 1000
    assert steps[5]["power_w"] < 1100             # far ahead: the daily pattern


def test_no_peeking_at_the_current_hour(conn):
    for m in range(0, 60):
        put(conn, DAY0 + 20 * 3600 + m * 60, 5000)
    # Still inside 20:xx: the 20:00 profile must not use its own unfinished hour.
    assert forecast.forecast(conn, "home")["steps"][0]["method"] == "now"


def test_accuracy_is_measured_against_the_meter(conn):
    put(conn, DAY0 + 20 * 3600, 1000)
    forecast.track(conn, "home")                   # writes down 20:00 forecast = 1000 W
    for m in range(1, 60):
        put(conn, DAY0 + 20 * 3600 + m * 60, 1200)  # reality: mostly 1200 W
    put(conn, DAY0 + 21 * 3600, 1200)
    forecast.track(conn, "home")                   # 21:00 -> score the 20:00 hour
    acc = forecast.accuracy(conn, "home")
    assert acc["hours"] == 1
    last = acc["last"]
    assert last["pred_w"] == 1000 and 1190 <= last["actual_w"] <= 1200
    assert 15 < last["err_pct"] < 18
