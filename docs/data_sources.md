# Data sources

| Data | Source | Status |
|---|---|---|
| House readings (6 rooms, 12 devices) | `simulator/sim.py`, **synthetic** | in use |
| Office building readings (10 rooms, 27 devices) | `simulator/sim.py --site building`, **synthetic** | in use |
| Starting meter value of the simulated house (286 kWh) | synthetic, chosen for the demo | in use |
| Lab room readings (incl. power factor) | ESP32 + PZEM-004T + PIR/DHT11/LDR, firmware in `firmware/wattwise` | Phase B |
| Power factor per device kind in the simulator (`KIND_PF`) | typical textbook values, **synthetic**; real PF comes from the PZEM | in use |
| Door / window contact | **simulated** (a push button on the device, a flag in the simulator) | in use |
| Device nameplate watts (`config/sites.json`, `rated_w`) | typical values, used only as a first guess; replaced by the measured step on the meter | in use |
| Household tariff tiers (`config/tariff.json`) | taken from the design, which cites the EMRC 2025 household tariff | **to verify against a real anonymized bill** |
| CO2 grid emission factor: 0.516 kg CO2/kWh (`config/tariff.json`) | IFI Dataset of Default Grid Factors v2.0 (Jul 2019), published by UNFCCC, Jordan, combined margin for energy efficiency | in use |
| Weather and solar radiation | Open-Meteo (free, no key, open data), `backend/weather.py`, default location Irbid | in use, optional: skipped when offline |
| LLM planner (optional) | Anthropic Claude API; it only receives the synthetic/sensor snapshot (rooms, watts, tariff, weather), never personal data | in use when a key is set |

No personal data is collected. The PIR only reports occupied/empty. No cameras.

## Open data used in the Phase 1 proposal

| Fact | Source |
|---|---|
| Jordan imported about 93% of its energy needs in 2018; national target of 9% better energy efficiency by 2030 | MEMR, Summary of the Comprehensive Strategy of the Energy Sector 2020-2030 |
| 2023: total electricity 19,113 GWh, households 46.3%, 1,664 kWh per capita | EMRC Statistical Bulletin 2023, via Jordan Times |
| 2025: total electricity 20,230 GWh, residential 45%, 2,622,457 subscribers | EMRC data, via Jordan News (Sep 2026) |
| CO2 factor for Jordan: 0.516 kg CO2/kWh (energy efficiency, combined margin) | IFI Dataset of Default Grid Factors v2.0 (Jul 2019), published by UNFCCC. Used in `config/tariff.json` |

Full links are in `docs/proposal/proposal_ar.md`, section "المراجع".
