# Data sources

| Data | Source | Status |
|---|---|---|
| House readings (6 rooms, 12 devices) | `simulator/sim.py`, **synthetic** | in use |
| Office building readings (10 rooms, 27 devices) | `simulator/sim.py --site building`, **synthetic** | in use |
| Starting meter value of the simulated house (286 kWh) | synthetic, chosen for the demo | in use |
| Lab room readings | ESP32 + PZEM-004T + PIR/DHT11/LDR | Phase B |
| Unlabeled devices for teach mode (`config/sites.json`, `sim.unlabeled`: watts and power factor) and the "stranger device" (60 W, pf 0.7) | `simulator/sim.py`, **synthetic**; the backend does not know them and must find them on the meter | in use |
| Device guess table (watts and power-factor ranges per appliance type, `backend/nilm.py`) | typical values from appliance nameplates and common measurements; only a guess that the user confirms or corrects | in use |
| Saved device fingerprints (name, room, watts, pf) | entered by the user in the chat, saved only after an explicit "yes"; no personal data | in use |
| Door / window contact | **simulated** (a push button on the device, a flag in the simulator) | in use |
| Device nameplate watts (`config/sites.json`, `rated_w`) | typical values, used only as a first guess; replaced by the measured step on the meter | in use |
| Household tariff tiers (`config/tariff.json`) | taken from the design, which cites the EMRC 2025 household tariff | **to verify against a real anonymized bill** |
| CO2 grid emission factor | official source to be chosen | **missing, shown as "—"** |
| Weather and solar radiation | Open-Meteo (free, no key, open data), `backend/weather.py`, default location Irbid | in use, optional: skipped when offline |
| LLM planner (optional) | Anthropic Claude API; it only receives the synthetic/sensor snapshot (rooms, watts, tariff, weather), never personal data | in use when a key is set |

No personal data is collected. The PIR only reports occupied/empty. No cameras.

## Open data used in the Phase 1 proposal

| Fact | Source |
|---|---|
| Jordan imported about 93% of its energy needs in 2018; national target of 9% better energy efficiency by 2030 | MEMR, Summary of the Comprehensive Strategy of the Energy Sector 2020-2030 |
| 2023: total electricity 19,113 GWh, households 46.3%, 1,664 kWh per capita | EMRC Statistical Bulletin 2023, via Jordan Times |
| 2025: total electricity 20,230 GWh, residential 45%, 2,622,457 subscribers | EMRC data, via Jordan News (Sep 2026) |
| Candidate CO2 factor for Jordan: 0.516 kg CO2/kWh (energy efficiency, combined margin) | IFI Dataset of Default Grid Factors v2.0 (Jul 2019), published by UNFCCC. Not yet adopted in `config/tariff.json` |

Full links are in `docs/proposal/proposal_ar.md`, section "المراجع".
