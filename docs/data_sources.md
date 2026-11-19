# Data sources

| Data | Source | Status |
|---|---|---|
| House readings (6 rooms, 12 devices) | `simulator/sim.py`, **synthetic** | in use |
| Starting meter value of the simulated house (286 kWh) | synthetic, chosen for the demo | in use |
| Lab room readings | ESP32 + PZEM-004T + PIR/DHT11/LDR | Phase B |
| Door / window contact | **simulated** (a push button on the device, a flag in the simulator) | in use |
| Device nameplate watts (`config/sites.json`, `rated_w`) | typical values, used only as a first guess; replaced by the measured step on the meter | in use |
| Household tariff tiers (`config/tariff.json`) | taken from the design, which cites the EMRC 2025 household tariff | **to verify against a real anonymized bill** |
| CO2 grid emission factor | official source to be chosen | **missing, shown as "—"** |
| Weather and solar radiation | Open-Meteo (free, no key, open data), `backend/weather.py`, default location Irbid | in use, optional: skipped when offline |
| LLM planner (optional) | Anthropic Claude API; it only receives the synthetic/sensor snapshot (rooms, watts, tariff, weather), never personal data | in use when a key is set |

No personal data is collected. The PIR only reports occupied/empty. No cameras.
