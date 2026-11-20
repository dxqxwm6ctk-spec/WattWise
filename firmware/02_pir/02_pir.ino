// Test 2: PIR motion sensor HC-SR501. It only says "someone moved" (no camera, no identity).
// Wiring: PIR VCC -> VIN (5V), GND -> GND, OUT -> GPIO27. Output is 3.3V, safe for the ESP32.
// Expected: wave your hand -> "occupied", stay still ~1 minute -> "empty".
// After power-up the PIR needs about 30-60 seconds to settle; ignore readings in that time.
// The two orange knobs on the PIR: Sx = sensitivity, Tx = how long it stays HIGH. Start with Tx fully left.

#define PIR_PIN 27
#define LED_GREEN 18

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(LED_GREEN, OUTPUT);
  Serial.println("Test 2: PIR. Wait 60 s for it to settle...");
}

void loop() {
  bool motion = digitalRead(PIR_PIN) == HIGH;
  digitalWrite(LED_GREEN, motion);
  Serial.println(motion ? "occupied (motion)" : "empty");
  delay(500);
}
