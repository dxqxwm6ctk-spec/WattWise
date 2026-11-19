"""The same agent on the 10-room building (config only, no code change)."""

import pytest

from backend import actions, agent, config, db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "WASTE_EMPTY_S", 0)
    monkeypatch.setattr(config, "ANALYZE_S", 0)
    agent._analyzing.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def reading(meeting_empty: bool):
    rooms = config.load_sites()["building"]["rooms"]
    return {"site": "building", "source": "simulator", "meter": {"power_w": 9000, "energy_kwh": 900.0},
            "rooms": [{"room_id": r["id"], "temp_c": 24.5, "light": 1200,
                       "occupied": False if (meeting_empty and r["id"] == "meeting") else r["sim"]["occupied"],
                       "window_open": meeting_empty and r["id"] == "meeting"} for r in rooms]}


def test_building_has_ten_rooms():
    assert len(config.load_sites()["building"]["rooms"]) == 10


def test_agent_works_on_the_building_and_never_touches_critical_loads(conn):
    actions.set_goal(conn, "building", "خفّف استهلاك المبنى بعد الدوام", None)
    actions.ingest(conn, reading(meeting_empty=True))
    asked = []
    for _ in range(40):
        agent.tick(conn, "building")
        a = actions.pending_approval(conn, "building")
        if a:
            asked.append(a["device_id"])
            actions.reject(conn, "building", a["id"])
    # Biggest waste first: the training-room AC (empty room), then others.
    assert asked and asked[0] == "trainAc"
    assert not {"serverRack", "serverAc", "officeFridge", "emergencyLight", "bldFireAlarm"} & set(asked)
    # Every rejected proposal left the device on.
    assert all(db.device(conn, "building", d)["is_on"] == 1 for d in asked)
