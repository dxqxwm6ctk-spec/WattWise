# WattWise: project brief for Claude Code

Read this whole file before doing anything. It is the single source of truth for the project. When something here conflicts with your own assumptions, this file wins. If something is missing or ambiguous, ask the user ONE short question instead of guessing.

## 0. Who you are working with (important)

- The user is the **team leader** of a student competition project. He is a **complete beginner** at electronics and has never wired a sensor or flashed a microcontroller. He is comfortable talking in **Jordanian Arabic**.
- **Talk to him in simple Jordanian-style Arabic** (clear, friendly, short sentences). Keep code, file names, comments in code, and commit messages in **English**.
- Explain every step as if he has never done it: what to plug where, what to click, what output he should see, and what to do if he does not see it. Give one small step at a time and wait for his result.
- He cannot be seen or touched by you, and you cannot see his hardware. Ask him for photos, serial-monitor output, or error text when debugging.
- **He must be able to explain every part of the project to the judges.** After each milestone, write a short "How this works" note (in Arabic, plain language) in `docs/explain/`. Prefer simple, readable code over clever code.
- The competition rule says all work must be done by the students. Never hide that AI tools are used; keep the code understandable and documented so he truly owns it. Remind him once to check with the organizers (ieeerasjadara@gmail.com) that using AI coding assistants is allowed.

## 1. The competition

**RoboCraft 2.0.0**, organized by IEEE RAS at Jadara University (Irbid), part of the Ibtikar Jadara conference. Sources: https://robocraft.ras-ju.com/ar and https://robocraft.ras-ju.com/ar/register?start=1

Our track: **02. Green Economy & Energy** (energy and resource efficiency, reducing environmental impact; an example problem is building energy efficiency: monitor loads, suggest actions, execute only what is approved).

### Hard requirements (a project missing ANY of them is eliminated in Phase 1)
1. **Goal:** the system takes a goal (not a question) and breaks it into steps by itself.
2. **Tools:** it uses at least two external tools (APIs, databases, files, messages, sensors, controllers).
3. **Real action:** it does something real outside the chat (switch a load, send an alert, produce a report).
4. **Human OK:** it pauses for human approval before sensitive or irreversible decisions.

### Not accepted
Plain chat interfaces without tools, classification/prediction notebooks without a surrounding system, mobile apps or websites without an agent, projects reused from a course or another competition.

### Other rules
- Connecting the agent to a robot or IoT device is optional but raises the score on the "agent depth" criterion.
- Data must be official open data, synthetic data, or anonymized data with written consent. **No personal data.** Document all data sources.
- The project must be original and built during the competition.
- Team of 2 to 4, at least one active IEEE member.

### Timeline (2026, deadlines are strict, late submissions are not accepted)
| Dates | Stage |
|---|---|
| 21.11 to 30.11 | Phase 1: proposal and proof of the problem (online) |
| 01.12 to 15.12 | Phase 2: working prototype (online) |
| 17.12 to 26.12 | Evaluation and submission |
| January 2027 | Final, on-site at Jadara University, Irbid |

Prize pool is 1000 JOD for the top three teams. The scoring rubric weights are not published.

## 2. The project in one paragraph

**WattWise** is an AI agent that lowers a small building's electricity use. It is given a goal such as "reduce this room's consumption by 15% this week without breaking comfort limits". It reads one power meter plus a few small sensors, learns what each load looks like, detects waste, forecasts consumption, plans actions, asks a human to approve, then switches real loads through relays, verifies the result with the meter, and reports the measured savings in dinars and kg of CO2. The 15% is a design target, never a claimed result; only report savings that were measured.

## 3. Final decisions (do not re-open these without asking the user)

These came out of a long discussion; they are settled.

1. **Budget is tight.** Use the cheapest design that still looks professional. Do not suggest buying extra hardware unless it is clearly essential. The user already has (or will have) an "ESP32 Upgraded Kit" from Temu plus **exactly ONE** PZEM-004T v3.0 10A energy sensor.
2. **One power meter only.** A single PZEM-004T measures the whole test circuit. The agent identifies each load by **load signatures** (a step change in watts when a relay switches a load). This is a lightweight non-intrusive load monitoring (NILM) feature and is a key "AI" showpiece.
3. **Two controlled loads** through the kit's 2-channel relay: a lamp (channel 1) and a small desk fan (channel 2). The fan stands in for air conditioning. Both are mains loads, so wiring them is done by an electrician (see section 9).
4. **No Telegram.** Telegram is blocked in Jordan. **Approval happens on a web page** served by our own backend (works from the phone on the local Wi-Fi, installable as a PWA). The demo must work with **no internet** on a local network or phone hotspot. Optional extra notification channels (for example ntfy) are nice-to-have and must never be required.
5. **The door is simulated** with a push button from the kit. Always label it as a simulated door contact in the UI and the docs. Say so honestly to the judges.
6. **Digital twin / simulator.** A pure-software building simulator (about 10 rooms, synthetic data, scenarios such as heat wave, holiday, sensor fault) lets us develop and demo before hardware arrives and shows the agent generalizes. It publishes readings through the **same API** as the real device, so the agent code is identical in both modes.
7. **Savings are measured professionally (M&V).** Build a baseline model of expected consumption (as a function of temperature, occupancy, hour) and compare with actual consumption. Never invent numbers.
8. **Safety rules are enforced in code, outside the LLM.** See section 6.

## 4. Hardware (what exists physically)

Already in the kit: ESP32 DevKit (Micro-USB), PIR HC-SR501, DHT11, LDR module (analog out), IR obstacle sensor (optional), 2-channel relay module (opto-isolated, verify it is rated 10A 250VAC; often active-LOW), LCD 1602 with I2C backpack, push buttons, buzzer, 5mm LEDs, RGB LED, resistors, jumper wires, breadboard, USB cable.

To be bought: 1x PZEM-004T v3.0 (10A, UART/Modbus), 5V USB adapter, mains-side parts (RCBO 2P 6A 30mA with a small enclosure, IP54 project box, 3x1.0 mm2 cable and plug, WAGO connectors), a lamp and a small fan (the user may reuse ones from home), one 470 uF capacitor across the 5V rail.

### Suggested ESP32 pin map (verify against the actual board before wiring; ask the user to read the silkscreen)
| Part | ESP32 pin | Notes |
|---|---|---|
| PZEM TX to ESP32 RX2 | GPIO16 | through a voltage divider: 1k from PZEM TX to the pin, 2k from the pin to GND, so 5V becomes about 3.3V. No level converter needed |
| PZEM RX from ESP32 TX2 | GPIO17 | 3.3V logic from the ESP32 is accepted by the PZEM |
| PZEM 5V and GND | VIN (5V) and GND | low-voltage (TTL) side only |
| Relay IN1 (lamp) | GPIO26 | probably active-LOW, test it |
| Relay IN2 (fan) | GPIO25 | probably active-LOW, test it |
| PIR HC-SR501 | GPIO27 | needs 5V power, output is 3.3V |
| DHT11 | GPIO4 | 10k pull-up if the module has none |
| LDR analog out (AO) | GPIO34 | input-only pin, fine |
| Door button (simulated) | GPIO32 | INPUT_PULLUP, pressed means "door open" |
| Emergency stop button | GPIO33 | INPUT_PULLUP, pressed means the agent is disabled and loads return to their normal state |
| Buzzer | GPIO23 | beeps when an approval is pending |
| Status LEDs green/yellow/red | GPIO18 / GPIO19 / GPIO5 | each with a 220 ohm resistor |
| LCD 1602 I2C | GPIO21 SDA, GPIO22 SCL | powered from 5V |

Build and test everything at low voltage on the breadboard FIRST. The mains parts come last and only through an electrician.

## 5. Architecture (keep it simple, one server, minimal dependencies)

```
ESP32 sensors  --HTTP JSON-->  FastAPI backend  <--  Simulator (same API)
                                   |
        +--------------------------+------------------------------+
        |              |                |               |
     SQLite DB     Agent loop      Web dashboard   Approval page (PWA)
                   (LLM + tools)   (live charts)   (Approve / Reject)
                        |
        Tools: read_sensors, get_forecast (Open-Meteo), get_tariff,
        detect_anomaly, forecast_load, propose_action, request_approval,
        control_relay, generate_report
                        |
        Policy Guard (hard rules, outside the LLM)  -->  relay commands to ESP32
```

- **Language and stack:** Python 3.11+, FastAPI, SQLite, plain HTML/JS with Chart.js for the frontend (no heavy framework), `scikit-learn` for the small models. Use HTTP between ESP32 and backend (the ESP32 POSTs readings and polls for relay commands). MQTT is optional and not needed.
- **LLM:** call a hosted LLM through its API with tool use. Read the key from an environment variable, never commit it. Add a clear spending cap and a **rule-based fallback** so the system keeps working if the API or the internet is down. Provide a clean abstraction so the model provider can be swapped.
- **ESP32 firmware:** Arduino C++ (PlatformIO or Arduino IDE). Libraries: WiFi, HTTPClient, ArduinoJson, PZEM-004T-v30, DHT, LiquidCrystal_I2C. Keep the firmware tiny and dumb: read, send, obey relay commands, show status. All intelligence lives in the backend.
- **Wi-Fi:** the ESP32 supports 2.4 GHz only.

### The three AI layers
1. **Anomaly detection:** learn normal consumption per load, per hour and occupancy state; flag deviations (for example, fan running while the room has been empty for a while). Isolation Forest or a rolling mean with deviation bounds is enough.
2. **Load forecasting and NILM-lite:** short-horizon forecast from time, temperature, occupancy and solar radiation; detect step changes in power to learn each load's signature and attribute consumption.
3. **LLM planner and explainer:** takes the goal, the analysis, the tariff and comfort limits; calls the tools; produces a decision plus a **plain Arabic explanation** (reason, numbers, alternative).

### Data sources
Sensors, Open-Meteo (free, no key) for weather and solar radiation, a tariff table that the user fills from a real anonymized Jordanian electricity bill (put it in a config file, never hardcode invented tariff numbers), and synthetic data from the simulator. Document every source in `docs/data_sources.md`.

## 6. Safety and policy (non-negotiable)

Permission tiers for agent actions:
| Tier | Examples | Who executes |
|---|---|---|
| 0, automatic | read sensors, analysis, recommendations, reports, alerts | the agent directly |
| 1, needs approval | switch the lamp or fan off/on, delay a load | the agent, only after the human approves on the web page |
| 2, forbidden | critical loads (fridges, fire alarms, medical devices, emergency lighting) | nobody; blocked in code |

Rules the **Policy Guard** must enforce in plain code, independent of the LLM:
- Only relays on an explicit **allowlist** can be switched.
- Comfort limits (min/max temperature) can never be violated.
- **No approval within the timeout means no action.** Silence is not consent.
- An **emergency-stop** (the physical button or a UI button) disables the agent and returns loads to their normal state.
- **Fail-safe:** on LLM failure, lost connection or a sensor fault, return loads to normal and keep a simple rule-based mode.
- Log every decision, its reason, its approval status and its outcome in an **audit log** shown in the UI.
- Privacy: the PIR only produces occupied/empty. No cameras, no tracking of people, no personal data.

## 7. What must be demonstrable (this is the judging story)

1. State the problem with real numbers (from a real bill, a one-week measurement, and open data).
2. A dashboard shows live consumption, occupancy, temperature, light, and the door state.
3. The user gives the agent a goal.
4. We create waste live (cover the PIR as "room empty" while the fan runs).
5. The agent detects it and shows the reasoning.
6. An approval card appears on the phone (web page), with a buzzer and a yellow LED on the device.
7. The user presses Approve and the relay switches the load off for real; the PZEM confirms the drop.
8. Pressing Reject must result in no action (proves condition 4).
9. A chart "without agent vs with agent" shows the measured saving (energy, dinars, CO2).
10. The simulator runs a 10-room building to show it scales.

## 8. Repository layout (create it)

```
wattwise/
  CLAUDE.md                this file
  TASKS.md                 living task list (you maintain it)
  README.md                setup and run instructions (Arabic + English)
  backend/                 FastAPI app, agent, tools, policy guard, models
  simulator/               digital twin that posts the same data as the ESP32
  firmware/                ESP32 Arduino sketches, one small test sketch per part
  frontend/                dashboard and approval page (PWA)
  docs/
    proposal/              Phase 1 proposal (Arabic)
    explain/               "how this works" notes in simple Arabic
    data_sources.md
    wiring.md              wiring guide for the beginner, step by step
  tests/
```

## 9. Phases and first actions

**Phase 0 (do this first):** read this file, then create `TASKS.md` with a checklist covering the phases below and keep it updated as you work. Then set up the repo skeleton and run the empty backend. Tell the user in Arabic what you did and what he should do next.

**Phase A (starts now, needs NO hardware):** backend skeleton, SQLite schema, simulator, dashboard with live charts, approval page, audit log, Policy Guard, rule-based fallback, then the agent loop with tools. Everything runs on synthetic data from the simulator.

**Phase B (when the kit arrives):** one tiny firmware test sketch per part (blink an LED, then PIR, DHT11, LDR, buttons, buzzer, LCD, relay with no mains attached, then the PZEM at low voltage in the lab only if safe). Give the user the wiring one connection at a time. Verify each part before moving on.

**Phase C (mains, with an electrician):** the electrician connects the 220 V side inside a closed enclosure with the RCBO. Before the first power-up, the electrician or a competent supervisor checks the wiring, and you remind the user of this. Never give step-by-step instructions for working on live mains wiring to a beginner.

**Phase D:** M&V baseline and savings report, the "how this works" notes, the Phase 1 proposal text, demo script, backup plan (local broker-free network, recorded demo video, a pre-generated report).

### Competition dates drive priorities
The Phase 1 proposal is due by 30.11 and needs a strong problem statement with evidence plus the agent design. Writing it can happen in parallel with Phase A. Hardware delays (shipping from Temu can take weeks) must never block the software.

## 10. Working style

- Work in small steps. After each step, run it and show the user how to verify it.
- Keep `TASKS.md` honest: tick only what is verified working.
- Write tests for the Policy Guard and the M&V calculation (these are the parts that must not be wrong).
- Never commit secrets or personal data. Use a `.env` file and `.env.example`.
- Do not add features nobody asked for. If you think something would help, say so in one line and let the user decide.
- When you are unsure about a hardware detail (pin labels, relay logic level, PZEM version), ask the user to read the label or send a photo instead of assuming.
