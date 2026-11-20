// Test 6: buzzer (beeps when an approval is waiting).
// Wiring: buzzer + (longer leg or marked "+") -> GPIO23, - -> GND.
// Works with both buzzer types:
//   active buzzer  (has a sticker / sealed bottom): beeps on its own when the pin is HIGH
//   passive buzzer (open green board underneath):   needs a tone, tone() gives it one
// Expected: two short beeps every 2 seconds.

#define BUZZER_PIN 23

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  Serial.println("Test 6: buzzer");
}

void beep(int ms) {
  tone(BUZZER_PIN, 2000);
  delay(ms);
  noTone(BUZZER_PIN);
  digitalWrite(BUZZER_PIN, LOW);
}

void loop() {
  beep(120);
  delay(120);
  beep(120);
  Serial.println("beep beep");
  delay(2000);
}
