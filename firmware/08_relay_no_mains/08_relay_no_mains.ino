// Test 8: the 2-channel relay module. NOTHING connected to the screw terminals. NO 220 V.
// Wiring (low-voltage side only): VCC -> VIN (5V), GND -> GND, IN1 -> GPIO26, IN2 -> GPIO25.
// Expected: every 2 seconds you hear a click and the small LED on the relay board changes.
//
// The question this test answers: is the module active-LOW?
// The Serial Monitor says which level the pin has. Look at the relay's LED:
//   relay LED ON when the pin is LOW  -> active-LOW  (most modules)  -> RELAY_ACTIVE_LOW true
//   relay LED ON when the pin is HIGH -> active-HIGH                 -> RELAY_ACTIVE_LOW false
// Tell the team the answer; the final sketch needs it.

#define RELAY1_PIN 26  // lamp
#define RELAY2_PIN 25  // fan

void setup() {
  Serial.begin(115200);
  // Set the level BEFORE making the pin an output, so the relay does not click at boot.
  digitalWrite(RELAY1_PIN, HIGH);
  digitalWrite(RELAY2_PIN, HIGH);
  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(RELAY2_PIN, OUTPUT);
  Serial.println("Test 8: relays (no mains attached!)");
}

void loop() {
  digitalWrite(RELAY1_PIN, LOW);
  Serial.println("IN1 = LOW   (is relay 1 LED on?)");
  delay(2000);
  digitalWrite(RELAY1_PIN, HIGH);
  Serial.println("IN1 = HIGH  (is relay 1 LED on?)");
  delay(2000);
  digitalWrite(RELAY2_PIN, LOW);
  Serial.println("IN2 = LOW   (is relay 2 LED on?)");
  delay(2000);
  digitalWrite(RELAY2_PIN, HIGH);
  Serial.println("IN2 = HIGH  (is relay 2 LED on?)");
  delay(2000);
}
