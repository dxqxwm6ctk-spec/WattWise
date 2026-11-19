"""The Policy Guard must never be wrong. These tests pin down every rule."""

from backend import config, policy

AC = {"id": "bedAc", "name": "AC", "kind": "ac", "tier": "T1", "allow": 1, "sensitive": 0}
LAMP = {"id": "lamp", "name": "Lamp", "kind": "light", "tier": "T1", "allow": 1, "sensitive": 0}
FRIDGE = {"id": "fridge", "name": "Fridge", "kind": "fridge", "tier": "T2", "allow": 0, "sensitive": 0}
ROUTER = {"id": "router", "name": "Router", "kind": "router", "tier": "T1", "allow": 0, "sensitive": 1}

EMPTY_ROOM = {"occupied": 0, "temp_c": 25.0, "light": 300}
HOT_OCCUPIED = {"occupied": 1, "temp_c": config.COMFORT_MAX_TEMP_C + 1, "light": 300}


def test_agent_may_switch_off_ac_in_empty_room():
    assert policy.check_switch(AC, False, policy.AGENT, EMPTY_ROOM).allowed


def test_critical_load_blocked_for_everyone():
    for actor in (policy.AGENT, policy.HUMAN):
        d = policy.check_switch(FRIDGE, False, actor, EMPTY_ROOM)
        assert not d.allowed and d.code == "critical_load"


def test_critical_kind_blocked_even_if_config_says_t1():
    fridge_typo = dict(FRIDGE, tier="T1", allow=1)
    assert not policy.check_switch(fridge_typo, False, policy.AGENT, EMPTY_ROOM).allowed
    assert not policy.check_switch(fridge_typo, False, policy.HUMAN, EMPTY_ROOM).allowed


def test_device_not_on_allowlist_blocked_for_agent_but_human_ok():
    manual_only = dict(LAMP, allow=0)
    assert policy.check_switch(manual_only, False, policy.AGENT, EMPTY_ROOM).code == "not_in_allowlist"
    assert policy.check_switch(manual_only, False, policy.HUMAN, EMPTY_ROOM).allowed


def test_sensitive_device_never_switched_by_agent():
    assert not policy.check_switch(dict(ROUTER, allow=1), False, policy.AGENT, EMPTY_ROOM).allowed


def test_estop_blocks_agent():
    assert policy.check_switch(AC, False, policy.AGENT, EMPTY_ROOM, estop=True).code == "estop_active"


def test_safe_mode_blocks_agent():
    assert policy.check_switch(AC, False, policy.AGENT, EMPTY_ROOM, safe_mode=True).code == "safe_mode"


def test_no_sensor_data_blocks_agent():
    assert policy.check_switch(AC, False, policy.AGENT, None).code == "no_sensor_data"


def test_comfort_max_temp_blocks_cooling_off_when_occupied():
    assert policy.check_switch(AC, False, policy.AGENT, HOT_OCCUPIED).code == "comfort_max_temp"


def test_cooling_off_allowed_when_hot_but_empty():
    room = dict(HOT_OCCUPIED, occupied=0)
    assert policy.check_switch(AC, False, policy.AGENT, room).allowed


def test_lamp_off_blocked_when_occupied_and_dark():
    room = {"occupied": 1, "temp_c": 24, "light": config.DARK_LIGHT_LEVEL - 1}
    assert policy.check_switch(LAMP, False, policy.AGENT, room).code == "comfort_dark"


def test_setpoint_comfort_band():
    assert policy.check_setpoint(AC, 24).allowed
    assert not policy.check_setpoint(AC, config.COMFORT_MIN_TEMP_C - 1).allowed
    assert not policy.check_setpoint(AC, config.COMFORT_MAX_TEMP_C + 1).allowed
    assert not policy.check_setpoint(LAMP, 24).allowed


def test_approval_timeout():
    t = config.APPROVAL_TIMEOUT_S
    assert not policy.approval_expired(100.0, 100.0 + t - 1)
    assert policy.approval_expired(100.0, 100.0 + t)
