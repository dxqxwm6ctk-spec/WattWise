"""Bill photo / manual bill analysis. No real LLM: a fake provider plays Claude."""

import base64

import pytest

from backend import actions, assistant, bill_reader, config, db, llm
from backend.actions import ActionError
from tests.test_flow import conn, reading  # noqa: F401  (conn is a fixture)

# A tiny valid PNG header is enough: the reader only checks the first bytes.
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


class FakeVision(llm.Provider):
    name, model = "fake", "fake-model"

    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls = data, error, []

    def read_image(self, system, prompt, image_b64, media_type, schema):
        self.calls.append(media_type)
        if self.error:
            raise self.error
        return self.data, llm.RunResult(input_tokens=1500, output_tokens=300)


def bill(**over):
    data = {"is_electricity_bill": True, "readable": True, "kwh": 450, "period_from": "2026-10-01",
            "period_to": "2026-10-31", "days": None, "amount_jod": 37.5, "energy_jod": 30.0,
            "tariff_type": "sub", "tiers": [], "other_charges": [], "explanation_ar": ["استهلكت ٤٥٠ ك.و.س."],
            "confidence": "high"}
    data.update(over)
    return data


@pytest.fixture
def home(conn):  # noqa: F811
    actions.ingest(conn, reading(800))
    return conn


def test_no_key_asks_for_manual_numbers(home):
    r = bill_reader.from_photo(home, "home", PNG)
    assert r["needs_manual"] and "ANTHROPIC_API_KEY" in r["message"]
    assert bill_reader.status(home)["photo"] is False


def test_manual_numbers_are_checked_against_the_tariff(home):
    r = bill_reader.from_manual(home, "home", 450, 30, 30)
    # sub tariff: 300 * 0.05 + 150 * 0.10 = 30 JD
    assert r["compare"]["tariff_energy_jod"] == 30.0
    assert r["compare"]["bill_kwh_per_day"] == 15.0
    assert any("150" in i for i in r["ideas"])   # 150 kWh above the cheaper tier
    assert r["by"] == "manual"


def test_manual_needs_kwh(home):
    with pytest.raises(ActionError):
        bill_reader.from_manual(home, "home", None, 30, 20)


def test_photo_is_read_and_only_numbers_are_kept(home):
    fake = FakeVision(bill())
    llm.set_provider(fake)
    r = bill_reader.from_photo(home, "home", "data:image/png;base64," + PNG)
    assert fake.calls == ["image/png"]
    assert r["by"] == "llm" and r["bill"]["days"] == 30          # from the period dates
    assert r["explanation"] == ["استهلكت ٤٥٠ ك.و.س."]
    kept = bill_reader.last_bill(home, "home")
    assert kept["kwh"] == 450 and set(kept) == {"kwh", "days", "amount_jod", "by", "ts"}
    stored = str(db.rows(home.execute("SELECT * FROM system_state"))) + str(db.rows(home.execute("SELECT * FROM audit_log")))
    assert PNG[:40] not in stored                                  # the photo itself is never saved
    assert llm.spent_usd(home) > 0                                 # counted against the monthly cap


def test_not_a_bill_falls_back_to_manual(home):
    llm.set_provider(FakeVision(bill(is_electricity_bill=False)))
    assert bill_reader.from_photo(home, "home", PNG)["needs_manual"]


def test_provider_error_falls_back_to_manual(home):
    llm.set_provider(FakeVision(error=llm.ProviderError("APIConnectionError")))
    assert bill_reader.from_photo(home, "home", PNG)["needs_manual"]


def test_budget_spent_means_no_photo_reading(home, monkeypatch):
    fake = FakeVision(bill())
    llm.set_provider(fake)
    monkeypatch.setattr(config, "LLM_MONTHLY_BUDGET_USD", 0)
    assert bill_reader.from_photo(home, "home", PNG)["needs_manual"] and fake.calls == []


def test_rejects_non_images_and_huge_files(home, monkeypatch):
    with pytest.raises(ActionError):
        bill_reader.from_photo(home, "home", base64.b64encode(b"%PDF-1.4 hello").decode())
    with pytest.raises(ActionError):
        bill_reader.from_photo(home, "home", "not base64!!")
    monkeypatch.setattr(config, "BILL_PHOTO_MAX_BYTES", 10)
    with pytest.raises(ActionError):
        bill_reader.from_photo(home, "home", PNG)


def test_why_bill_compares_with_the_last_bill(home):
    bill_reader.from_manual(home, "home", 450, 30, 30)
    w = assistant.why_bill(home, "home")
    assert any("فاتورتك الأخيرة" in c["what"] for c in w["causes"])
