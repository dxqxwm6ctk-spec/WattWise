# Pin map used by every sketch

Check every number against the silkscreen on YOUR board before wiring. If a label
is different, change the `#define` at the top of the sketch, not the wire.

| Part | ESP32 pin |
|---|---|
| PZEM TX -> ESP32 RX2 (through 1k / 2k divider) | GPIO16 |
| PZEM RX <- ESP32 TX2 | GPIO17 |
| Relay IN1 (lamp) | GPIO26 |
| Relay IN2 (fan) | GPIO25 |
| PIR HC-SR501 OUT | GPIO27 |
| DHT11 DATA | GPIO4 |
| LDR module AO | GPIO34 |
| Door button (SIMULATED door contact) | GPIO32 |
| Emergency stop button | GPIO33 |
| Buzzer | GPIO23 |
| LED green / yellow / red (each with 220 ohm) | GPIO18 / GPIO19 / GPIO5 |
| LCD 1602 I2C SDA / SCL | GPIO21 / GPIO22 |
