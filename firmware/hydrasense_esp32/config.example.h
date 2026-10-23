// =============================================================================
// HydraSense ESP32 Station — LOCAL CONFIGURATION (secrets live here)
//
//   1. Copy this file and rename the copy to  config.h
//      (Arduino IDE: File > Save As into this same folder)
//   2. Fill in YOUR values below.
//   3. config.h is listed in .gitignore — it is NEVER committed to git.
//
// NEVER commit your real Wi-Fi password or MQTT credentials to the repository.
// =============================================================================
#pragma once

// ---- Wi-Fi (2.4 GHz only — ESP32 cannot use 5 GHz) ----
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// ---- MQTT broker = YOUR WINDOWS PC's LAN IPv4 address ----
//   Find it on the PC:   ipconfig   → "IPv4 Address" under your Wi-Fi adapter
//   It will look like 192.168.1.x — NOT localhost, NOT 127.0.0.1,
//   and NOT the ESP32's own IP (192.168.1.7).
#define MQTT_HOST     "192.168.1.100"
#define MQTT_PORT     1883
// Leave both as "" if the broker allows anonymous connections (default).
#define MQTT_USER     ""
#define MQTT_PASSWORD ""

// ---- Station identity (must already exist in the backend database) ----
//   Seeded stations: "ARK-001", "ARK-002", "ARK-003".
//   Unknown station codes are REJECTED by the backend and never stored.
//   DEVICE_ID identifies the physical device; it must be unique per station.
#define STATION_CODE  "ARK-001"
#define DEVICE_ID     "ESP32-HS-001"

// ---- Publish cadence (backend accepts anything in the 1–60 s range) ----
#define PUBLISH_INTERVAL_MS 3000UL

// ---- NTP time (needed for honest ISO-8601 timestamps; UTC) ----
#define NTP_SERVER_1  "pool.ntp.org"
#define NTP_SERVER_2  "time.google.com"

// =============================================================================
// CALIBRATION — KEEP EVERY FLAG AT 0 UNTIL REAL REFERENCE CALIBRATION IS DONE
// =============================================================================
// While a flag is 0 the firmware publishes NULL for that sensor's engineering
// value and reports raw ADC + voltage in the diagnostics block instead. It
// NEVER invents pH/NTU/ppm numbers from unmeasured constants.
//
// pH (two-point calibration with real buffer solutions):
//   Measure the probe voltage in pH 7.00 buffer  → CAL_PH_V7
//   Measure the probe voltage in pH 4.00 buffer  → CAL_PH_V4
//   Then set PH_CALIBRATED to 1.
#define PH_CALIBRATED        0
#define CAL_PH_V7            2.50
#define CAL_PH_V4            3.00

// Turbidity (two-point with 0 NTU and a known standard, e.g. 100 NTU):
// The firmware already publishes a LIVE provisional relative index (0-100)
// from ADS1115 A2 that needs no calibration; these flags/constants are only
// for a future real-NTU calibration. The index is NEVER labelled NTU.
#define TURBIDITY_CALIBRATED 0
#define CAL_TURB_V0          2.50
#define CAL_TURB_V100        1.00

// TDS: keep 0 until your exact TDS module model is confirmed. The voltage →
// ppm conversion depends on the module's output characteristics; the firmware
// deliberately does NOT guess it. After confirming the datasheet, implement
// tdsConvert() in hydrasense_esp32.ino and flip this flag to 1.
#define TDS_CALIBRATED       0
