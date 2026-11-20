// Test 5: the two push buttons.
//   GPIO32 = SIMULATED door contact (pressed = "door open"). Always say "simulated" to the judges.
//   GPIO33 = emergency stop (pressed = agent disabled, loads back to normal).
// Wiring: one leg of each button to its pin, the other leg to GND. No resistor needed:
// INPUT_PULLUP keeps the pin HIGH, pressing pulls it LOW.
// Expected: pressing a button prints it and lights the red LED.

#define DOOR_PIN 32
#define ESTOP_PIN 33
#define LED_RED 5

void setup() {
  Serial.begin(115200);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  pinMode(ESTOP_PIN, INPUT_PULLUP);
  pinMode(LED_RED, OUTPUT);
  Serial.println("Test 5: buttons");
}

void loop() {
  bool door = digitalRead(DOOR_PIN) == LOW;
  bool estop = digitalRead(ESTOP_PIN) == LOW;
  digitalWrite(LED_RED, door || estop);
  Serial.printf("door(simulated)=%s  estop=%s\n", door ? "OPEN" : "closed", estop ? "PRESSED" : "-");
  delay(300);
}
