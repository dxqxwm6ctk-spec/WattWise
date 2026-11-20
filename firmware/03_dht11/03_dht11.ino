// Test 3: DHT11 temperature and humidity.
// Library: "DHT sensor library" by Adafruit (install it with "Adafruit Unified Sensor").
// Wiring (3-pin module): + -> 3V3, - -> GND, OUT/S -> GPIO4.
// A bare 4-pin sensor needs a 10k resistor between DATA and 3V3; most modules already have it.
// Expected: about every 2 s a line like "temp 24.0 C  humidity 41 %".
// "failed to read" every time = check the DATA wire and the pin number.

#include <DHT.h>

#define DHT_PIN 4
DHT dht(DHT_PIN, DHT11);

void setup() {
  Serial.begin(115200);
  dht.begin();
  Serial.println("Test 3: DHT11");
}

void loop() {
  delay(2000);  // the DHT11 is slow: at most one reading every 2 seconds
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    Serial.println("failed to read from DHT11");
    return;
  }
  Serial.printf("temp %.1f C  humidity %.0f %%\n", t, h);
}
