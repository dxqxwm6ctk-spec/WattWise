# Firmware (ESP32, Arduino IDE)

One tiny test sketch per part, then the final sketch. Do them **in order**, and do not
move on until the current one shows the expected output. Every sketch says at the top
what to wire and what you should see in the Serial Monitor (115200 baud).

| Folder | Tests | Needs library |
|---|---|---|
| `01_blink_leds` | board, cable, upload, 3 LEDs | - |
| `02_pir` | motion sensor (occupied / empty only) | - |
| `03_dht11` | temperature + humidity | DHT sensor library (Adafruit) |
| `04_ldr` | light level | - |
| `05_buttons` | simulated door button + emergency stop | - |
| `06_buzzer` | buzzer | - |
| `07_lcd` | LCD 1602 I2C (also prints its address) | LiquidCrystal I2C (Frank de Brabander) |
| `08_relay_no_mains` | relays clicking, active-LOW or not. **No 220 V attached** | - |
| `09_pzem` | PZEM-004T communication; real numbers only after the electrician wires 220 V | PZEM-004T-v30 (Jakub Mandula) |
| `wattwise` | final sketch: sends readings, obeys relay commands, fail-safe | ArduinoJson v7 + all above |

Pins: `pins.md` (check them against your board). Step-by-step wiring in Arabic: `docs/wiring.md`.

## Arduino IDE setup (once)
1. Install Arduino IDE 2.
2. File > Preferences > "Additional boards manager URLs":
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. Tools > Board > Boards Manager: install **esp32 by Espressif Systems** (version 3.x).
4. Tools > Board: **ESP32 Dev Module**. Tools > Port: the COM port that appears when you plug the board in.
   No port? Install the USB driver (CP210x or CH340, read the chip name near the USB socket).
5. Sketch > Include Library > Manage Libraries: install the libraries from the table.

## Final sketch
1. In `wattwise/`, copy `config.example.h` to `config.h` and fill in Wi-Fi, laptop IP, relay logic, LCD address.
2. Start the backend on the laptop so other devices can reach it: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`. Allow it through the Windows firewall when asked.
3. Upload `wattwise.ino`. The LCD shows the ESP32's IP, then the watts.
4. Open `http://localhost:8000/index.html?site=lab`: the readings appear every second.

What the firmware sends (`POST /api/readings`):
```json
{"site": "lab", "source": "device", "estop_pressed": false,
 "meter": {"power_w": 85.2, "energy_kwh": 0.42, "voltage_v": 229.8, "current_a": 0.41, "freq_hz": 50.0, "pf": 0.90},
 "rooms": [{"room_id": "lab", "temp_c": 24.0, "humidity": 41, "light": 1830, "occupied": false, "window_open": false}]}
```
`window_open` comes from the push button: it is a **simulated** door contact.

The sketches were written before the kit arrived and were not compiled here (no ESP32 toolchain
in the dev sandbox). If the IDE shows an error, send the exact error text.
