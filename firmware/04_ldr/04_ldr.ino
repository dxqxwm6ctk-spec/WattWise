// Test 4: light sensor (LDR module, analog output AO).
// Wiring: VCC -> 3V3 (NOT 5V, the pin only accepts up to 3.3V), GND -> GND, AO -> GPIO34.
// Expected: a number 0..4095. Cover the sensor with your hand and the number changes a lot.
// On many modules the number goes UP when it gets darker. Write down both values for the team.

#define LDR_PIN 34

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);  // 0..4095
  Serial.println("Test 4: LDR");
}

void loop() {
  Serial.printf("light raw = %d\n", analogRead(LDR_PIN));
  delay(500);
}
