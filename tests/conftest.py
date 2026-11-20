"""Shared test setup: never call a real LLM or the internet from the tests."""

import pytest

from backend import config, connectivity, llm


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "WEATHER_ENABLED", False)
    llm.set_provider(None)
    monkeypatch.setattr(connectivity, "probe", lambda: True)   # tests start "online"
    connectivity.reset_for_tests(online=True)
    yield
    llm.set_provider(None)
