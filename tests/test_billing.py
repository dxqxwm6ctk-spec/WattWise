"""Bill math against a small hand-made tariff (independent of the real config values)."""

import pytest

from backend import billing

TARIFF = {"types": {"t": {"display_max_kwh": 700, "who": "", "label": "",
                          "tiers": [[300, 0.05], [600, 0.10], [None, 0.20]]}}}


@pytest.mark.parametrize("kwh, expected", [
    (0, 0.0),
    (100, 5.0),                       # 100 * 0.05
    (300, 15.0),                      # 300 * 0.05
    (400, 25.0),                      # 15 + 100 * 0.10
    (700, 15.0 + 30.0 + 20.0),        # 300*0.05 + 300*0.10 + 100*0.20
])
def test_bill_for(kwh, expected):
    assert billing.bill_for(kwh, TARIFF, "t") == pytest.approx(expected)


def test_marginal_price():
    assert billing.marginal_price(10, TARIFF, "t") == 0.05
    assert billing.marginal_price(300, TARIFF, "t") == 0.05
    assert billing.marginal_price(301, TARIFF, "t") == 0.10
    assert billing.marginal_price(5000, TARIFF, "t") == 0.20


def test_tier_info_warns_near_next_tier():
    info = billing.tier_info(290, 320, TARIFF, "t")
    assert "100 فلس" in info["message"]
    assert sum(s["width_pct"] for s in info["segments"]) == pytest.approx(100, abs=0.5)
