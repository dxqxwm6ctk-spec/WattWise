# WattWise

وكيل ذكاء اصطناعي بيقلّل استهلاك الكهرباء: بيقرأ العدّاد والحسّاسات، بيكشف الهدر، بيطلب موافقتك، وبعدين بيطفي الجهاز وبيتأكد من التوفير بالعدّاد.

An AI agent that lowers a building's electricity use. It reads one power meter and a few sensors, detects waste, asks a human to approve, switches the load, then verifies the saving with the meter. Built for RoboCraft 2.0.0 (Green Economy & Energy track).

## Run it (no hardware needed)

One command for the whole demo (backend + house + 10-room building):

```bash
pip install -r requirements.txt
python scripts/run_demo.py --fresh
```

The demo script and backup plan (Arabic) are in `docs/demo/demo_script_ar.md`.

Or step by step:

```bash
pip install -r requirements.txt

# 1) the backend (also serves the web pages)
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 2) in a second terminal: the simulated house (synthetic data)
python -m simulator.sim

# 3) optional, a third terminal: the simulated 10-room office building
python -m simulator.sim --site building
```

Open:
- Dashboard: http://localhost:8000/index.html (building: `index.html?site=building`)
- Interactive 3D house (three.js, works offline) + guided "how it works" tour: http://localhost:8000/house.html (`?site=building`, `?site=lab`)
- Phone app: Flutter, in `mobile/` (see `mobile/README.md`)
- Savings report (print to PDF): http://localhost:8000/api/sites/home/report
- Web backup of the phone page: http://localhost:8000/app.html
  From a phone on the same Wi-Fi, use the laptop's IP, for example `http://192.168.1.10:8000/app.html`.

### طريقة التجربة بالعربي
1. شغّل الأمرين فوق، وافتح لوحة التحكم.
2. اكتب الهدف واضغط «أعطِ الوكيل الهدف».
3. اضغط «١ · غرفة النوم فاضية والشباك مفتوح».
4. بعد ثواني بتطلع بطاقة «بدنا رأيك» على الهاتف. اضغط «إيه، طفّيه» أو «لا، خلّيه».
5. شوف سجل القرارات والتوفير المُقاس بالفاتورة.

## Online copy on Render (optional)

The demo never needs the internet. For an optional hosted copy, Render reads the
Blueprint in `render.yaml` and runs `python scripts/cloud_start.py` (backend on `$PORT` plus the
simulators, synthetic data only). Every push to `main` redeploys it, no laptop needed.
Live server: https://wattwise-vysn.onrender.com/index.html (free plan: it sleeps after about 15 minutes
without visitors and takes about a minute to wake up). Steps in Arabic: `docs/deploy/render_ar.md`.

## AI planner (optional)

Without an API key everything runs on the rule-based planner (works offline).
To let the LLM split the goal into a plan and explain each proposal, copy
`.env.example` to `.env` and set `ANTHROPIC_API_KEY`. The monthly spending cap is
`LLM_MONTHLY_BUDGET_USD` (default 5 USD); when it is reached, or the API is down
or late, the agent falls back to the rules by itself. The LLM never switches a
device: the Policy Guard and your approval still decide. Requests opt in to the
API's server-side fallback model, so a declined request is retried on another model.

## Tests

```bash
python -m pytest -q
```

## Layout

| Folder | What |
|---|---|
| `backend/` | FastAPI app, agent loop, Policy Guard, approvals, bill math |
| `simulator/` | digital twin that posts the same data as the ESP32 |
| `frontend/` | dashboard (HTML/JS + Chart.js) and the web backup of the phone page (PWA) |
| `mobile/` | owner's phone app (Flutter), see `mobile/README.md` |
| `config/` | sites, rooms, devices, tariff |
| `firmware/` | ESP32 sketches (Phase B) |
| `docs/` | proposal, "how this works" notes, demo script, data sources, wiring |
| `scripts/` | `run_demo.py` (start everything), `record_demo_video.py` (backup video) |
| `tests/` | Policy Guard, billing, agent flow, LLM layer (fake provider), anomaly detection, forecast, building, M&V and report |

## API (same for the ESP32 and the simulator)

- `POST /api/readings`: `{site, meter:{power_w, energy_kwh, voltage_v, current_a, freq_hz}, rooms:[{room_id, temp_c, light, occupied, window_open}], estop_pressed}`
- `GET /api/sites/{site}/commands`: relay states, set points, `approval_pending` (buzzer + yellow LED), `estop`
- `POST /api/sites/{site}/command/parse` and `/command/run` `{text}`: plain-Arabic orders (run only after the user confirms)
- `GET|POST /api/sites/{site}/schedules`, `POST /api/sites/{site}/timers`: on/off timers and daily schedules
- `POST /api/sites/{site}/heater/suggest` and `/heater/apply`: smart water-heater schedule
- `GET /api/sites/{site}/why` and `/weekly.txt`: bill analysis and the weekly report
- `GET /api/sites/{site}/state`: everything the dashboard and the app show
- `POST /api/sites/{site}/goal`, `/approvals/{id}/approve`, `/approvals/{id}/reject`, `/estop`, `/reset`, `/devices/{id}/toggle`, `/devices/{id}/setpoint`

## Honesty notes
- The house is simulated: all its data is synthetic. The door/window contact is simulated (a push button on the real device).
- Savings are counted only after the meter confirms the drop. The 15% is a target, not a result.
- Tariff tiers in `config/tariff.json` must be verified against a real bill. CO2 stays "—" until an official factor is filled in.
- AI coding assistants were used to help write this code; every part is documented so the team can explain it.
