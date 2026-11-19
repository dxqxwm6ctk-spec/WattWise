# Firmware (Phase B)

ESP32 sketches go here, one tiny test sketch per part (LED, PIR, DHT11, LDR,
buttons, buzzer, LCD, relay without mains, then the PZEM-004T).

The final sketch only reads sensors, POSTs them to `/api/readings` with
`"site": "lab"`, polls `/api/sites/lab/commands` and obeys the relay states.
All intelligence stays in the backend.
