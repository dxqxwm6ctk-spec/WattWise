# WattWise tasks

Tick only what is verified working. Deadlines: Phase 1 proposal 30.11, prototype 15.12.

## Phase 0: setup
- [x] Read CLAUDE.md, create this file
- [x] Repo skeleton (backend, simulator, firmware, frontend, docs, tests)
- [x] Backend runs (`uvicorn backend.main:app`), `/api/health` answers
- [ ] Ask the organizers (ieeerasjadara@gmail.com) to confirm AI coding assistants are allowed (draft ready: `docs/outreach/organizers_email_ai_tools.md`, team sends it)

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
- [x] Tests: Policy Guard, bill math, end-to-end agent flow, LLM layer, anomaly detection, forecast, 10-room building, M&V and report, schedules and commands (88 passing)
- [x] Flutter phone app with the 4 screens from the design (home, devices, bill, safety), same API (tested as a web build against the simulator)
- [ ] Run the Flutter app on a real Android phone on the local Wi-Fi
- [x] LLM planner + explainer with tool use, spending cap, provider abstraction, rule-based fallback (tested with a fake provider; 38 tests passing)
- [ ] Try the LLM planner with a real API key (team puts the key in `.env`)
- [x] Open-Meteo weather tool (optional when offline; offline path verified, online call not reachable from the dev sandbox)
- [x] Anomaly detection: residual (meter minus known signatures) learned per hour and occupancy with running mean/std; alert-only; simulator scenario "unknown_load"
- [x] Short-horizon load forecast (now + hourly profile blend, accuracy measured against the meter every hour; weather not used yet)
- [ ] Lab-mode page polish (the design's "WattWise.dc.html")
- [x] Simulator: 10-room office building as a third site (`--site building`), config only, same agent code
- [x] New design: goal in plain words -> plan with T0/T1 tags, approval card shows the gentler alternative
- [x] Rule-based goal reading (`backend/goal.py`): percent, bill, rooms, device kinds, period, comfort; the plan differs per goal and the named rooms/kinds are handled first; "15%" no longer read as 15 JD
- [x] Power factor in the load signature (`backend/nilm.py`): meter `pf`, step PF learned at verification and in add-device, (P, Q) matching; simulator sends a synthetic PF; dashboard shows PF
- [x] Typed/spoken commands (rule-based Arabic parsing), each action checked by the Policy Guard, runs only after confirm (mic via the browser in the web pages)
- [x] Timers and daily on/off schedules run in the backend, checked when saved and again when they fire; smart water-heater schedule suggestion (max 3 h window)
- [x] "Why is my bill like this?" analysis and a weekly text report to download
- [x] Same features in the phone web page and the Flutter app (new Schedules tab); AC set temperature removed from the UI (on/off only)
- [x] Interactive 3D house page (`house.html`, three.js bundled offline): realistic rooms, furniture, lighting and day/night, animated devices, energy flow, click-to-zoom, approval card, NILM step recognition, guided "how it works" tour that drives the real system; phone mockup on the dashboard moved behind a "معاينة الموبايل" button
- [x] Home EV charger (simulated 7.4 kW): session recognised by its meter step, measured kWh, start/end notifications, smart-charging proposal (evening peak, approval, resume timer), excluded from savings
- [ ] Show the interactive house inside the Flutter app (WebView or native)
- [ ] Voice input inside the Flutter app (needs a speech package; the web pages already have the mic)

## Data to fill (team)
- [ ] Verify tariff tiers in `config/tariff.json` against a real, anonymized bill
- [x] CO2 grid emission factor for Jordan: 0.516 kg/kWh, IFI dataset v2.0 (UNFCCC), in `config/tariff.json`
- [ ] One week of real measurements for the problem statement

## Phase B: hardware at low voltage (when the kit arrives)
- [ ] Blink LED, then PIR, DHT11, LDR, buttons, buzzer, LCD
- [ ] Relay test with NO mains attached (check active-LOW)
- [ ] PZEM-004T at low voltage in the lab only if safe
- [ ] Final firmware: POST readings, poll commands (written in `firmware/wattwise`, plus test sketches 01-09 and `docs/wiring.md`; compiled by CI only, not yet on a board)

## Phase C: mains (electrician only)
- [ ] Electrician wires the 220 V side in a closed box with the RCBO
- [ ] Wiring checked by the electrician / supervisor before first power-up

## Phase D: proof and story
- [x] M&V baseline model (Ridge on hour, occupancy, temperature; ASHRAE G14 checks; refuses to report when data or model is not good enough) + tests
- [x] Savings report: `/api/sites/{site}/report` (HTML, print to PDF); sample from the simulator in project files
- [ ] "How this works" notes for every part (`docs/explain/`)
- [ ] Phase 1 proposal text (Arabic) in `docs/proposal/` (draft written; placeholders for bill, measurement, team still open)
- [x] Demo script and backup plan (`docs/demo/demo_script_ar.md`), one-command launcher (`scripts/run_demo.py`), fonts vendored for offline, recorded backup video and pre-generated report in project files
- [ ] Team rehearses the demo twice and times it
- [x] Optional online copy: `.railway/railway.py` (was `railway.json`) + `scripts/cloud_start.py` (backend on `$PORT` + simulators), tested locally the Railway way
- [ ] Online copy actually deployed on Railway (needs the user's Railway account; steps in `docs/deploy/railway_ar.md`)
