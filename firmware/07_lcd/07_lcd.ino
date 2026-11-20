// Test 7: LCD 1602 with the I2C backpack.
// Library: "LiquidCrystal I2C" by Frank de Brabander.
// Wiring: GND -> GND, VCC -> VIN (5V), SDA -> GPIO21, SCL -> GPIO22.
// First the sketch scans the I2C bus and prints the address it finds (usually 0x27 or 0x3F).
// If the screen lights up but shows nothing: turn the small blue screw on the back (contrast).
// If the address is not 0x27, change LCD_ADDR below and upload again.

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define LCD_ADDR 0x27
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  Serial.println("Test 7: scanning I2C...");
  for (byte a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) Serial.printf("found I2C device at 0x%02X\n", a);
  }
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("WattWise");
  lcd.setCursor(0, 1);
  lcd.print("LCD test OK");
}

void loop() {
  lcd.setCursor(13, 1);
  lcd.print((millis() / 1000) % 1000);
  delay(1000);
}
