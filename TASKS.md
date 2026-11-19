# WattWise tasks

Tick only what is verified working. Deadlines: Phase 1 proposal 30.11, prototype 15.12.

## Phase 0: setup
- [x] Read CLAUDE.md, create this file
- [x] Repo skeleton (backend, simulator, firmware, frontend, docs, tests)
- [x] Backend runs (`uvicorn backend.main:app`), `/api/health` answers
- [ ] Ask the organizers (ieeerasjadara@gmail.com) to confirm AI coding assistants are allowed

## Phase A: software, no hardware
- [x] SQLite schema (rooms, devices, meter/room readings, approvals, audit log, goals)
- [x] Simulator (digital twin of a 6-room house) posting through the same API as the ESP32
- [x] Scenarios: bedroom empty + window open, heat wave, holiday, sensor fault
- [x] Policy Guard in plain code: allowlist, T2 critical loads, comfort limits, estop, safe mode, fail-safe
- [x] Approval flow: request, approve, reject, timeout = no action
- [x] Audit log shown in the UI
- [x] Rule-based planner (waste = load on in an empty room), with Arabic explanation and numbers
- [x] Goal input: the agent splits it into 7 steps and shows their live status
- [x] Verification with the meter after each action; measured step becomes the load signature (NILM-lite)
- [x] Measured savings (kWh, JOD) from verified actions only; baseline line = actual + verified held-off loads
- [x] Add-device flow: measure a new device's signature on the main meter
- [x] Dashboard (plain HTML/JS + Chart.js) implementing the "WattWise Home" design
- [x] Web approval page (PWA, works offline on the local network) as backup for the Flutter app
- [x] Tests: Policy Guard, bill math, end-to-end agent flow (29 passing)
- [ ] Flutter phone app with the 4 screens from the design (home, devices, bill, safety), same API
- [ ] LLM planner + explainer with tool use, spending cap, provider abstraction, rule-based fallback
- [ ] Open-Meteo weather tool (optional when offline)
- [ ] Anomaly detection model (rolling mean / Isolation Forest per load, hour, occupancy)
- [ ] Short-horizon load forecast
- [ ] Lab-mode page polish (the design's "WattWise.dc.html")
- [ ] Simulator: scale to ~10 rooms (config only)

## Data to fill (team)
- [ ] Verify tariff tiers in `config/tariff.json` against a real, anonymized bill
- [ ] Official CO2 grid emission factor for Jordan, with source
- [ ] One week of real measurements for the problem statement

## Phase B: hardware at low voltage (when the kit arrives)
- [ ] Blink LED, then PIR, DHT11, LDR, buttons, buzzer, LCD
- [ ] Relay test with NO mains attached (check active-LOW)
- [ ] PZEM-004T at low voltage in the lab only if safe
- [ ] Final firmware: POST readings, poll commands

## Phase C: mains (electrician only)
- [ ] Electrician wires the 220 V side in a closed box with the RCBO
- [ ] Wiring checked by the electrician / supervisor before first power-up

## Phase D: proof and story
- [ ] M&V baseline model (temperature, occupancy, hour) + tests
- [ ] Savings report (PDF/HTML)
- [ ] "How this works" notes for every part (`docs/explain/`)
- [ ] Phase 1 proposal text (Arabic) in `docs/proposal/`
- [ ] Demo script and backup plan (offline network, recorded video, pre-generated report)
