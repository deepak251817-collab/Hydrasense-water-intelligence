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
// pH (two-point calibration with real buffer solutions, measured at the
// ADS1115 input — this IS the CAL_PH_Vx unit; fold in any divider yourself):
//   Measure the probe voltage in pH 7.00 buffer  → CAL_PH_V7
//   Measure the probe voltage in pH 4.01 buffer  → CAL_PH_V4 (must be > V7)
//   Then set PH_CALIBRATED to 1. The firmware fits
//   slope = (CAL_PH_V7 − CAL_PH_V4)/3 at boot and rejects an implausible fit.
//   Example from real preliminary buffer measurements at an ADS1115 divider
//   junction (UNVERIFIED — replace with your own fresh measurements):
//     CAL_PH_V7 ≈ 1.246 V, CAL_PH_V4 ≈ 1.484 V  →  ≈ 79.3 mV/pH.
#define PH_CALIBRATED        0
#define CAL_PH_V7            2.50
#define CAL_PH_V4            3.00

// pH slope temperature compensation (Nernst term) driven by the DS18B20.
// Default OFF — enabling it changes screening inputs and must be recorded in
// docs/FEATURE_STATUS.md together with a justification.
#define PH_TEMP_COMPENSATION 0

// Turbidity: the firmware already publishes a LIVE provisional relative index
// (0-100) from ADS1115 A2 that needs no calibration; the index is NEVER
// labelled NTU and is never compared with NTU limits. TURBIDITY_CALIBRATED is
// currently a PLACEHOLDER: no NTU lookup table or conversion is implemented,
// so setting it to 1 changes nothing except a boot-time reminder. A future
// NTU upgrade must be built as a piecewise lookup from formazin/reference
// standards (0, 20, 100, 800 NTU), not a single straight line.
#define TURBIDITY_CALIBRATED 0
#define CAL_TURB_V0          2.50
#define CAL_TURB_V100        1.00

// TDS: set TDS_CALIBRATED to 1 ONLY after recording >= 4 real reference
// standards below. The firmware fits a second-order polynomial (least
// squares, checked against every point within +/−20%) through the standards
// at boot; measurements are compensated to 25 °C with k = 1 + 0.02*(T−25)
// using the DS18B20. Published values are NaCl-EQUIVALENT conductivity in
// mg/L. Define BOTH of these in config.h when calibrating:
//   const size_t TDS_CAL_COUNT  = 4;
//   const float  TDS_CAL_POINTS[][2] = {   // {voltage_v_at_ADS1115, mg/L NaCl}
//     {0.045f,    0.0f},    // distilled / rinsed probe in 0 mg/L solution
//     {0.655f,  250.0f},
//     {1.180f,  500.0f},
//     {2.100f, 1000.0f},
//   };
// Example pair 0.655 V -> 250 mg/L is illustrative, NOT a datasheet value —
// measure YOUR standards before enabling.
#define TDS_CALIBRATED       0
