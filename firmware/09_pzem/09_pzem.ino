// Test 9: PZEM-004T v3.0 energy meter, LOW-VOLTAGE side only.
// Library: "PZEM-004T-v30" by Jakub Mandula.
//
// IMPORTANT: the PZEM measures only when its other side is wired to 220 V. That side is wired
// by the electrician inside the closed box. Without it, this test only checks the
// communication: you will see "no answer" or NaN values until mains is connected. That is normal.
//
// Wiring (TTL side, 4 pins):  5V -> VIN,  GND -> GND,
//   PZEM RX <- GPIO17 (direct),
//   PZEM TX -> 1k resistor -> GPIO16, and a 2k resistor from GPIO16 to GND (5V becomes ~3.3V).
//
// Expected with mains and a load on: voltage ~230 V, power in W, and the power factor PF.
// PF ~1.00 for a normal lamp or heater, lower (e.g. 0.6-0.9) for a fan. WattWise uses PF to tell them apart.

#include <PZEM004Tv30.h>

#define PZEM_RX_PIN 16  // ESP32 receives here (from PZEM TX)
#define PZEM_TX_PIN 17  // ESP32 sends here (to PZEM RX)

PZEM004Tv30 pzem(Serial2, PZEM_RX_PIN, PZEM_TX_PIN);

void setup() {
  Serial.begin(115200);
  Serial.println("Test 9: PZEM-004T");
}

void loop() {
  float v = pzem.voltage();
  if (isnan(v)) {
    Serial.println("no answer from the PZEM (normal if 220 V is not connected yet; else check TX/RX)");
  } else {
    Serial.printf("V=%.1f  A=%.3f  W=%.1f  kWh=%.3f  Hz=%.1f  PF=%.2f\n",
                  v, pzem.current(), pzem.power(), pzem.energy(), pzem.frequency(), pzem.pf());
  }
  delay(1000);
}
