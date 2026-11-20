// WattWise final firmware for the lab room. Tiny and "dumb" on purpose:
//   1. read the sensors and the PZEM meter,
//   2. POST them to the backend every second   (POST /api/readings, site "lab"),
//   3. ask the backend what the relays should be (GET /api/sites/lab/commands) and obey,
//   4. show the status on the LEDs, the buzzer and the LCD.
// All the intelligence (AI, Policy Guard, approvals) lives in the backend.
//
// Safety in the firmware itself:
//   - Emergency stop button: relays go back to NORMAL at once, even without Wi-Fi.
//   - No answer from the backend for FAILSAFE_MS: relays go back to NORMAL.
//   - "NORMAL" = both loads ON (that is how the room works without the agent).
//
// Libraries: ArduinoJson (v7), PZEM-004T-v30, DHT sensor library, LiquidCrystal I2C.
// Before uploading: copy config.example.h to config.h and fill it in.

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <PZEM004Tv30.h>
#include <DHT.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "config.h"

// ---- pins (see firmware/pins.md) ----
#define PZEM_RX_PIN 16
#define PZEM_TX_PIN 17
#define RELAY_LAMP_PIN 26
#define RELAY_FAN_PIN 25
#define PIR_PIN 27
#define DHT_PIN 4
#define LDR_PIN 34
#define DOOR_PIN 32   // SIMULATED door contact (push button)
#define ESTOP_PIN 33
#define BUZZER_PIN 23
#define LED_GREEN 18
#define LED_YELLOW 19
#define LED_RED 5

const char* SITE = "lab";
const char* ROOM = "lab";
const unsigned long SEND_EVERY_MS = 1000;
const unsigned long FAILSAFE_MS = 15000;      // same idea as STALE_READING_S in the backend
const unsigned long PIR_HOLD_MS = 60000;      // "occupied" stays true for 1 min after the last motion

PZEM004Tv30 pzem(Serial2, PZEM_RX_PIN, PZEM_TX_PIN);
DHT dht(DHT_PIN, DHT11);
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);

// Desired relay states (true = load ON). Start in the normal state.
bool lampOn = true, fanOn = true;
bool approvalPending = false, agentStopped = false;
unsigned long lastOk = 0, lastSend = 0, lastMotion = 0, lastDht = 0;
float tempC = NAN, humidity = NAN;
float lastPower = NAN;

// ---------- relays ----------
void writeRelay(int pin, bool on) {
  bool level = RELAY_ACTIVE_LOW ? !on : on;
  digitalWrite(pin, level ? HIGH : LOW);
}

void applyRelays() {
  writeRelay(RELAY_LAMP_PIN, lampOn);
  writeRelay(RELAY_FAN_PIN, fanOn);
}

void backToNormal() {
  lampOn = true;
  fanOn = true;
  applyRelays();
}

// ---------- Wi-Fi ----------
void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lcd.clear();
  lcd.print("WiFi...");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(250);
    if (digitalRead(ESTOP_PIN) == LOW) backToNormal();
  }
  lcd.clear();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi OK, IP %s\n", WiFi.localIP().toString().c_str());
    lcd.print(WiFi.localIP().toString());
  } else {
    Serial.println("WiFi failed, will retry");
    lcd.print("No WiFi");
  }
}

// ---------- one reading -> backend ----------
bool sendReading(bool estopPressed) {
  JsonDocument doc;
  doc["site"] = SITE;
  doc["source"] = "device";
  doc["estop_pressed"] = estopPressed;

  JsonObject meter = doc["meter"].to<JsonObject>();
  float p = pzem.power();
  if (isnan(p)) {
    // No answer from the PZEM: send nothing, the backend's stale-data rule goes fail-safe.
    Serial.println("PZEM: no answer");
    return false;
  }
  lastPower = p;
  meter["power_w"] = p;
  meter["energy_kwh"] = pzem.energy();
  meter["voltage_v"] = pzem.voltage();
  meter["current_a"] = pzem.current();
  meter["freq_hz"] = pzem.frequency();
  meter["pf"] = pzem.pf();  // power factor: helps tell the lamp from the fan

  JsonObject room = doc["rooms"].to<JsonArray>().add<JsonObject>();
  room["room_id"] = ROOM;
  if (!isnan(tempC)) room["temp_c"] = tempC;
  if (!isnan(humidity)) room["humidity"] = humidity;
  room["light"] = analogRead(LDR_PIN);
  room["occupied"] = millis() - lastMotion < PIR_HOLD_MS;   // only occupied / empty, nothing else
  room["window_open"] = digitalRead(DOOR_PIN) == LOW;        // SIMULATED door contact

  String body;
  serializeJson(doc, body);
  HTTPClient http;
  http.begin(String(SERVER_URL) + "/api/readings");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(3000);
  int code = http.POST(body);
  http.end();
  if (code != 200) Serial.printf("POST failed: %d\n", code);
  return code == 200;
}

// ---------- backend -> relay states ----------
bool pollCommands() {
  HTTPClient http;
  http.begin(String(SERVER_URL) + "/api/sites/" + SITE + "/commands");
  http.setTimeout(3000);
  int code = http.GET();
  if (code != 200) {
    http.end();
    Serial.printf("GET commands failed: %d\n", code);
    return false;
  }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getString());
  http.end();
  if (err) return false;
  lampOn = doc["relays"]["lamp"] | true;
  fanOn = doc["relays"]["fan"] | true;
  approvalPending = doc["approval_pending"] | false;
  agentStopped = doc["estop"] | false;
  applyRelays();
  return true;
}

// ---------- status: LEDs, buzzer, LCD ----------
void showStatus(bool online) {
  digitalWrite(LED_GREEN, online && !approvalPending && !agentStopped);
  digitalWrite(LED_YELLOW, approvalPending);
  digitalWrite(LED_RED, !online || agentStopped);
  if (approvalPending && (millis() / 500) % 4 == 0) tone(BUZZER_PIN, 2000, 80);

  lcd.setCursor(0, 0);
  char line[17];
  if (isnan(lastPower)) snprintf(line, sizeof line, "--- W %s       ", online ? "" : "OFF");
  else snprintf(line, sizeof line, "%5.0fW %4.1fC    ", lastPower, isnan(tempC) ? 0.0 : tempC);
  lcd.print(line);
  lcd.setCursor(0, 1);
  if (agentStopped) lcd.print("STOP: agent off ");
  else if (!online) lcd.print("No server: SAFE ");
  else if (approvalPending) lcd.print("Approve on phone");
  else {
    snprintf(line, sizeof line, "L:%s F:%s       ", lampOn ? "on " : "off", fanOn ? "on " : "off");
    lcd.print(line);
  }
}

void setup() {
  Serial.begin(115200);
  // Relay pins: set the "normal" level before enabling the output, so nothing clicks at boot.
  writeRelay(RELAY_LAMP_PIN, true);
  writeRelay(RELAY_FAN_PIN, true);
  pinMode(RELAY_LAMP_PIN, OUTPUT);
  pinMode(RELAY_FAN_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  pinMode(ESTOP_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  analogReadResolution(12);
  dht.begin();
  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcd.print("WattWise lab");
  connectWifi();
  lastOk = millis();
}

void loop() {
  unsigned long now = millis();
  if (digitalRead(PIR_PIN) == HIGH) lastMotion = now;

  // Emergency stop works locally, before anything else, even with no Wi-Fi.
  bool estop = digitalRead(ESTOP_PIN) == LOW;
  if (estop) backToNormal();

  if (now - lastDht >= 2000) {   // the DHT11 is slow
    lastDht = now;
    float t = dht.readTemperature(), h = dht.readHumidity();
    if (!isnan(t)) tempC = t;
    if (!isnan(h)) humidity = h;
  }

  if (now - lastSend >= SEND_EVERY_MS) {
    lastSend = now;
    connectWifi();
    bool ok = WiFi.status() == WL_CONNECTED && sendReading(estop) && !estop && pollCommands();
    if (ok || (estop && WiFi.status() == WL_CONNECTED)) lastOk = now;
    if (millis() - lastOk > FAILSAFE_MS) {
      backToNormal();   // fail-safe: no server -> no agent decisions
      approvalPending = false;
    }
    showStatus(millis() - lastOk <= FAILSAFE_MS);
  }
}
