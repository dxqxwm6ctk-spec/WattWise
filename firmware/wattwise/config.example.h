// Copy this file to "config.h" (same folder) and fill in your values.
// config.h is in .gitignore: never commit your Wi-Fi password.

#pragma once

// 2.4 GHz Wi-Fi only (the ESP32 cannot see 5 GHz). A phone hotspot works.
#define WIFI_SSID "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// The laptop that runs the backend, on the same Wi-Fi. Find its IP with "ipconfig" (Windows).
#define SERVER_URL "http://192.168.1.10:8000"

// From test 08: true if the relay LED turns on when the pin is LOW.
#define RELAY_ACTIVE_LOW true

// From test 07: the address the I2C scan printed.
#define LCD_ADDR 0x27
