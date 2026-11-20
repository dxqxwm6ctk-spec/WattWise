// Test 1: the three status LEDs. Proves the board, the USB cable and the upload work.
// Expected: green, yellow, red light up one after the other, forever.
// Serial Monitor at 115200 prints which LED is on.

#define LED_GREEN 18
#define LED_YELLOW 19
#define LED_RED 5

const int leds[] = {LED_GREEN, LED_YELLOW, LED_RED};
const char* names[] = {"green", "yellow", "red"};

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 3; i++) pinMode(leds[i], OUTPUT);
  Serial.println("Test 1: LEDs");
}

void loop() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(leds[i], HIGH);
    Serial.printf("%s ON\n", names[i]);
    delay(600);
    digitalWrite(leds[i], LOW);
  }
}
