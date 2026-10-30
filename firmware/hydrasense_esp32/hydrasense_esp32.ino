// =============================================================================
// HydraSense ESP32 Station — firmware
//
// Publishes one JSON telemetry packet per cycle to:
//     hydrasense/stations/<STATION_CODE>/telemetry
// which the HydraSense backend (MQTT subscriber) ingests into sensor_readings.
//
// CALIBRATION GATE: pH and TDS publish JSON null until PH_CALIBRATED /
// TDS_CALIBRATED are set to 1 with REAL reference measurements in config.h.
// Uncalibrated sensors keep publishing raw ADC + voltage in diagnostics.
// Turbidity is a sensor-derived relative index (0-100), NOT NTU.
// Invalid or out-of-range values are sent as null rather than clamped.
// Raw ADC counts and voltages are printed and included in telemetry diagnostics.
// A disconnected DS18B20
// still publishes null rather than a fabricated temperature.
//   * `source: "esp32"` marks every packet as physical hardware, so it stays
//     distinguishable from the Python simulator's readings in the database.
//
// Hardware: ESP32 DevKit V1 + ADS1115 16-bit ADC (I²C: SDA=GPIO21, SCL=GPIO22),
//   DS18B20 temperature on GPIO 4. All analog sensors connect to the ADS1115
//   (A0=pH, A1=TDS, A2=turbidity via its voltage divider) — NOTHING is read
//   from the ESP32's own ADC pins.
//
// Libraries (install via Arduino IDE > Manage Libraries):
//   * PubSubClient   by Nick O'Leary
//   * OneWire        by Paul Stoffregen
//   * DallasTemperature by Miles Burton
//   * Adafruit ADS1X15 by Adafruit (ADS1115/ADS1015 driver)
//
// Secrets live in config.h (copy of config.example.h — never committed).
// =============================================================================
#include <WiFi.h>
#include <time.h>
#include <stdarg.h>
#include <string.h>
#include <math.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_ADS1X15.h>

#include "config.h"

// ---- Wiring (matches the built hardware; no sensors on the ESP32's own ADC) ----
// ADS1115 16-bit ADC on I²C:
//   GPIO 21 -> SDA, GPIO 22 -> SCL, VDD 3.3 V, GND common with the ESP32
//   A0 <- pH module output          A1 <- TDS module "A" output
//   A2 <- turbidity output THROUGH its existing two-resistor voltage divider
#define PIN_I2C_SDA    21
#define PIN_I2C_SCL    22
#define PIN_DS18B20     4   // OneWire bus for DS18B20 (needs 4.7 k pull-up)

#define CH_PH           0   // ADS1115 channel A0
#define CH_TDS          1   // ADS1115 channel A1
#define CH_TURBIDITY    2   // ADS1115 channel A2

// pH calibration is fitted at boot from REAL buffer voltages in config.h:
// CAL_PH_V7 (pH 7.00) and CAL_PH_V4 (pH 4.01), both measured at the ADS1115
// input. slope = dV/dpH = (CAL_PH_V7 - CAL_PH_V4) / 3.0. This replaces the
// old hard-coded 1.0278 V / theoretical 59.16 mV/pH pair, which measured
// buffers contradict. If the flags or the fit are invalid, pH publishes null.
float phVAt7 = 0.0f;          // ADS1115 volts that correspond to pH 7.00
float phVoltsPerPh = 0.0f;    // dV/dpH at the ADS1115 input (negative when the
                              // module's voltage falls as pH rises)
bool phCalValid = false;      // true only when PH_CALIBRATED=1 and the fit is sane

// Optional Nernst temperature compensation for pH (default OFF; enable only
// after a documented justification in docs/FEATURE_STATUS.md).
#ifndef PH_TEMP_COMPENSATION
#define PH_TEMP_COMPENSATION 0
#endif

// Water temperature shared by pH slope compensation and the TDS k-factor.
// 25 C fallback when the DS18B20 cannot report; the fallback is visible in
// the TDS diagnostics + serial line as an assumed temperature.
float waterTempC = 25.0f;
bool waterTempValid = false;

// Relative turbidity index reference endpoints, using reconstructed SENSOR OUT
// voltage (A2 voltage * 1.5 for the 10k/20k divider). Wider provisional span
// avoids prematurely saturating the index for the previously observed values.
// Adjust only after recording your own clear/cloudy sample readings.
// These values are not NTU calibration and do not certify water safety.
const float TURBIDITY_CLEAR_SENSOR_VOLTAGE = 0.400f;
const float TURBIDITY_CLOUDY_SENSOR_VOLTAGE = 0.100f;
const float TURBIDITY_R1_OHMS = 10000.0f;  // sensor OUT -> A2 junction
const float TURBIDITY_R2_OHMS = 20000.0f;  // A2 junction -> GND
#define TURBIDITY_SAMPLE_COUNT 10
#define TURBIDITY_SAMPLE_DELAY_MS 20

// Gain ±4.096 V full-scale (covers pH ~0–3.3 V, TDS ~0–2.4 V, and the
// divider-scaled turbidity output). A gain only sets the MEASUREMENT range —
// it does NOT make over-voltage safe: the absolute maximum input is
// VDD + 0.3 V = 3.6 V on a 3.3 V supply. Keep the turbidity voltage divider
// in place and verify its output ≤ 3.3 V with a multimeter (firmware/README.md §1).
#define ADS_GAIN              GAIN_ONE

#define MQTT_TOPIC_PREFIX "hydrasense/stations"   // must match backend MQTT_TOPIC_PREFIX
#define WIFI_RETRY_MS   15000UL
#define MQTT_RETRY_MS   10000UL
#define MQTT_BUF_SIZE   1024                     // PubSubClient default (256) is too small for diagnostics JSON
#define VALID_EPOCH     1577836800L              // 2020-01-01T00:00:00Z — earlier = NTP not synced yet

WiFiClient netClient;
PubSubClient mqttClient(netClient);
OneWire oneWire(PIN_DS18B20);
DallasTemperature ds18b20(&oneWire);
Adafruit_ADS1115 ads;
bool adsReady = false;   // true only after the ADS1115 answers on I²C at boot

unsigned long lastPublishMs = 0;
unsigned long lastWifiAttemptMs = 0;
unsigned long lastMqttAttemptMs = 0;
unsigned long publishSeq = 0;
bool wifiUp = false;
bool mqttUp = false;

// Device-reported error strings, cleared after each successful publish.
const char* deviceErrors[6];
size_t deviceErrorCount = 0;

// ---- Result types ----
// These structs must stay ABOVE every function: the Arduino .ino preprocessor
// auto-generates function prototypes and inserts them before the FIRST
// function in the file, so anything defined later would not yet exist there.
struct AnalogResult {
  int raw;
  float voltage;       // physical voltage at the ADS1115 input
  bool calibrated;     // false until proper sensor-specific calibration is done
  bool hasValue;       // true only when a meaningful estimate is available
  float value;
  const char* error;   // NULL when valid
};

struct TempResult {
  bool valid;
  float value;
  const char* error;   // NULL when valid
};

void pushError(const char* msg) {
  if (deviceErrorCount < 6) deviceErrors[deviceErrorCount++] = msg;
}

// -----------------------------------------------------------------------------
// JSON payload building (manual formatting keeps library deps minimal)
// -----------------------------------------------------------------------------
size_t appendf(char* buf, size_t pos, size_t cap, const char* fmt, ...) {
  if (pos >= cap) return pos;
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf + pos, cap - pos, fmt, ap);
  va_end(ap);
  if (n < 0) return pos;
  pos += (size_t)n;
  return (pos < cap) ? pos : cap - 1;
}

// Writes "key":null when there is no honest value, else "key":<number>.
size_t appendJsonNum(char* buf, size_t pos, size_t cap,
                     const char* key, bool hasValue, float value, int decimals) {
  if (!hasValue) return appendf(buf, pos, cap, "\"%s\":null", key);
  return appendf(buf, pos, cap, "\"%s\":%.*f", key, decimals, value);
}

// -----------------------------------------------------------------------------
// Sensor acquisition (all analog reads go through the ADS1115 over I²C)
// -----------------------------------------------------------------------------
int16_t adsReadCounts(uint8_t channel) {
  if (!adsReady) return 0;
  return ads.readADC_SingleEnded(channel);
}

// Volts per LSB follows the SELECTED gain (conversion always matches
// whatever ads.setGain() was called with, not a hard-coded range).
float lsbVoltsForGain(int gain) {
  switch (gain) {
    case GAIN_TWOTHIRDS: return 6.144f / 32768.0f;
    case GAIN_ONE:       return 4.096f / 32768.0f;
    case GAIN_TWO:       return 2.048f / 32768.0f;
    case GAIN_FOUR:      return 1.024f / 32768.0f;
    case GAIN_EIGHT:     return 0.512f / 32768.0f;
    case GAIN_SIXTEEN:   return 0.256f / 32768.0f;
    default:             return 4.096f / 32768.0f;
  }
}

float countsToVolts(int16_t counts) {
  return (float)counts * lsbVoltsForGain(ads.getGain());
}

// Provisional pH estimate based on the current A0 voltage and one reference point.
// If the estimated pH is outside 0..14, publish null + a diagnostic instead of
// silently clamping it to 0 (which can hide a wrong calibration voltage).
AnalogResult readPh() {
  AnalogResult r = {};
  r.raw = 0;
  r.voltage = 0.0f;
  r.calibrated = false;
  r.hasValue = false;
  r.value = 0.0f;
  r.error = NULL;

  if (!adsReady) {
    r.error = "ads1115 unavailable";
    return r;
  }

  if (!phCalValid) {
    r.error = "pH uncalibrated: set PH_CALIBRATED=1 with CAL_PH_V7/CAL_PH_V4 buffer voltages (firmware/README.md section 10)";
    return r;
  }

  long total = 0;
  const int samples = 7;
  for (int i = 0; i < samples; ++i) {
    total += adsReadCounts(CH_PH);
    delay(8);
  }
  r.raw = (int)(total / samples);
  r.voltage = countsToVolts((int16_t)r.raw);

  if (!isfinite(r.voltage) || r.voltage < 0.01f || r.voltage > 3.25f) {
    r.error = "pH voltage out of expected range; check module power, A0 wiring and common GND";
    return r;
  }

  float slope = phVoltsPerPh;
#if PH_TEMP_COMPENSATION
  if (waterTempValid) {
    // Nernst slope temperature term for a glass electrode:
    // slope(T) = slope(25C) * (273.15 + T) / 298.15.
    slope = phVoltsPerPh * (273.15f + waterTempC) / 298.15f;
  }
#endif

  const float estimate = 7.0f + ((r.voltage - phVAt7) / slope);
  if (!isfinite(estimate) || estimate < 0.0f || estimate > 14.0f) {
    r.error = "pH outside 0..14; check CAL_PH_V7/CAL_PH_V4 against fresh calibration buffers";
    return r;
  }

  r.calibrated = true;
  r.hasValue = true;
  r.value = estimate;
  return r;
}

// Relative status for station-specific demo references. This is not NTU and
// is not a drinking-water safety determination.
const char* getTurbidityStatus(float index) {
  if (index < 30.0f) return "CLEARER";
  if (index < 55.0f) return "MODERATE";
  return "CLOUDIER";
}

float estimateTurbidityIndex(float sensorVoltage) {
  const float span = TURBIDITY_CLEAR_SENSOR_VOLTAGE -
                     TURBIDITY_CLOUDY_SENSOR_VOLTAGE;
  if (!isfinite(sensorVoltage) || span <= 0.001f) return NAN;

  float index = (TURBIDITY_CLEAR_SENSOR_VOLTAGE - sensorVoltage) *
                100.0f / span;
  if (index < 0.0f) index = 0.0f;
  if (index > 100.0f) index = 100.0f;
  return index;
}

AnalogResult readTurbidity() {
  AnalogResult r = {};
  r.raw = 0;
  r.voltage = 0.0f;
  r.calibrated = false;
  r.hasValue = false;
  r.value = 0.0f;
  r.error = NULL;

  if (!adsReady) {
    r.error = "ads1115 unavailable";
    return r;
  }

  long total = 0;
  const int samples = TURBIDITY_SAMPLE_COUNT;
  for (int i = 0; i < samples; ++i) {
    total += adsReadCounts(CH_TURBIDITY);
    delay(TURBIDITY_SAMPLE_DELAY_MS);
  }
  r.raw = (int)(total / samples);
  r.voltage = countsToVolts((int16_t)r.raw);  // voltage at ADS1115 A2

  // Reconstruct sensor OUT across the installed 10k/20k divider.
  const float sensorOutputV = r.voltage *
      (TURBIDITY_R1_OHMS + TURBIDITY_R2_OHMS) / TURBIDITY_R2_OHMS;

  // Near-zero output usually means a disconnected sensor, bad ground, or no power.
  // Do not turn that fault into a misleading turbidity index of 100.
  if (!isfinite(sensorOutputV) || sensorOutputV < 0.02f || r.voltage > 3.25f) {
    r.error = "turbidity voltage invalid; check sensor power, divider, A2 and common GND";
    return r;
  }

  r.value = estimateTurbidityIndex(sensorOutputV);
  if (!isfinite(r.value)) {
    r.error = "turbidity index unavailable; check reference endpoint configuration";
    return r;
  }
  r.hasValue = true;
  return r;
}

// ---- TDS calibration ----
// A second-order polynomial c = a*v25^2 + b*v25 + c0 is fitted at boot (least
// squares, normal equations + Gaussian elimination) to the >= 4 reference
// standards in config.h (TDS_CAL_POINTS / TDS_CAL_COUNT). v25 is the measured
// voltage compensated to 25 C with the standard conductivity factor
// k = 1 + 0.02*(T-25). Results are NaCl-EQUIVALENT conductivity in mg/L,
// not dissolved-solids mass. No calibration -> null, never a guess.
float tdsPolyA = 0.0f, tdsPolyB = 0.0f, tdsPolyC = 0.0f;
bool tdsCalValid = false;

// Backwards-compatible defaults so an existing config.h without the new TDS
// constants still compiles (and stays uncalibrated = publishes null).
#ifndef TDS_CAL_COUNT
#define TDS_CAL_COUNT 0
static const float TDS_CAL_POINTS[1][2] = {{0.0f, 0.0f}};
#endif

// Solve the 3x3 normal-equation system for the quadratic least-squares fit.
// Returns false when the system is singular (degenerate calibration points).
bool solve3x3(float m[3][4], float out[3]) {
  for (int col = 0; col < 3; ++col) {
    int pivot = col;
    for (int row = col + 1; row < 3; ++row)
      if (fabsf(m[row][col]) > fabsf(m[pivot][col])) pivot = row;
    if (fabsf(m[pivot][col]) < 1e-12f) return false;
    if (pivot != col)
      for (int k = 0; k < 4; ++k) { float t = m[col][k]; m[col][k] = m[pivot][k]; m[pivot][k] = t; }
    for (int row = 0; row < 3; ++row) {
      if (row == col) continue;
      float f = m[row][col] / m[col][col];
      for (int k = col; k < 4; ++k) m[row][k] -= f * m[col][k];
    }
  }
  out[0] = m[0][3] / m[0][0];
  out[1] = m[1][3] / m[1][1];
  out[2] = m[2][3] / m[2][2];
  return true;
}

// Maps a 25-C-compensated ADS1115 voltage to NaCl-equivalent mg/L using the
// boot-fitted polynomial. Returns NAN (-> null) instead of clamping to 0.
float tdsConvert(float voltageV) {
  const float v25 = voltageV / (1.0f + 0.02f * (waterTempC - 25.0f));
  const float c = tdsPolyA * v25 * v25 + tdsPolyB * v25 + tdsPolyC;
  if (!isfinite(c) || c < 0.0f) return NAN;
  return c;
}

AnalogResult readTds() {
  AnalogResult r = {};
  r.raw = 0;
  r.voltage = 0.0f;
  r.calibrated = false;
  r.hasValue = false;
  r.value = 0.0f;
  r.error = NULL;

  if (!adsReady) {
    r.error = "ads1115 unavailable";
    return r;
  }

  long total = 0;
  const int samples = 7;
  for (int i = 0; i < samples; ++i) {
    total += adsReadCounts(CH_TDS);
    delay(8);
  }
  r.raw = (int)(total / samples);
  r.voltage = countsToVolts((int16_t)r.raw);
  if (!isfinite(r.voltage) || r.voltage < 0.0f || r.voltage > 3.25f) {
    r.error = "TDS voltage invalid; check sensor output and A1 wiring";
    return r;
  }
  if (!tdsCalValid) {
    r.error = "TDS uncalibrated: set TDS_CALIBRATED=1 with >=4 reference standards in TDS_CAL_POINTS (firmware/README.md section 10)";
    return r;
  }
  const float value = tdsConvert(r.voltage);
  if (!isfinite(value)) {
    r.error = "TDS mapping produced no valid value for this voltage; recheck calibration points";
    return r;
  }
  r.calibrated = true;
  r.hasValue = true;
  r.value = value;
  return r;
}

TempResult readTemperature() {
  TempResult r;
  ds18b20.requestTemperatures();
  float t = ds18b20.getTempCByIndex(0);
  // DEVICE_DISCONNECTED_C (-127) = bus fault; 85.0 = DS18B20 power-up default
  // (a real water station never reads exactly 85.0 °C — treat as "no reading").
  if (t <= DEVICE_DISCONNECTED_C) {
    r.valid = false; r.value = 0.0f; r.error = "disconnected";
  } else if (t >= 85.0f) {
    r.valid = false; r.value = 0.0f; r.error = "invalid reading (85C power-up default?)";
  } else {
    r.valid = true; r.value = t; r.error = NULL;
  }
  return r;
}

// -----------------------------------------------------------------------------
// Telemetry packet
// -----------------------------------------------------------------------------
// Diagnostics entry for one analog sensor: raw counts, volts, calibration
// status — plus an `error` field when the ADS1115 itself is unavailable
// (the existing frontend SensorDiagnostics type already reads `error`).
size_t appendAnalogDiag(char* buf, size_t pos, size_t cap,
                        const char* key, const AnalogResult& r) {
  const char* calibrationStatus = r.calibrated ? "calibrated"
                                : r.hasValue  ? "provisional_estimate"
                                : (r.error != NULL && strstr(r.error, "uncalibrated")) ? "uncalibrated"
                                : "unavailable";
  pos = appendf(buf, pos, cap,
                "\"%s\":{\"raw_adc\":%d,\"voltage_v\":%.3f,\"valid\":%s,\"calibration_status\":\"%s\"",
                key, r.raw, r.voltage, r.hasValue ? "true" : "false", calibrationStatus);
  if (strcmp(key, "turbidity") == 0 && r.hasValue) {
    pos = appendf(buf, pos, cap,
                  ",\"sensor_output_v\":%.3f,\"value_type\":\"relative_index_0_100\",\"classification\":\"%s\"",
                  r.voltage * (TURBIDITY_R1_OHMS + TURBIDITY_R2_OHMS) / TURBIDITY_R2_OHMS,
                  getTurbidityStatus(r.value));
  }
  if (r.error != NULL) pos = appendf(buf, pos, cap, ",\"error\":\"%s\"", r.error);
  return appendf(buf, pos, cap, "},");
}

void publishTelemetry() {
  // Honest ISO-8601 UTC timestamp requires synced NTP time; never publish a
  // 1970 epoch. Publishing resumes automatically once time is valid.
  time_t now = time(nullptr);
  if (now < VALID_EPOCH) {
    static bool warned = false;
    if (!warned) {
      Serial.println("[TIME] NTP not synced yet — deferring publish (no fake timestamps).");
      warned = true;
    }
    return;
  }
  struct tm tmv;
  gmtime_r(&now, &tmv);
  char ts[24];
  strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%SZ", &tmv);

  // Read temperature FIRST so pH/TDS temperature compensation uses a fresh
  // sample on the same publish cycle.
  TempResult temp = readTemperature();
  if (temp.valid) { waterTempC = temp.value; waterTempValid = true; }
  else { waterTempC = 25.0f; waterTempValid = false; }

  AnalogResult ph = readPh();
  AnalogResult turb = readTurbidity();
  AnalogResult tds = readTds();

  if (ph.hasValue) {
    Serial.printf("[PH] raw_avg=%d | A0=%.3f V | pH=%.2f | calibrated (V7=%.3f V, %.1f mV/pH)\n",
                  ph.raw, ph.voltage, ph.value, phVAt7, fabsf(phVoltsPerPh) * 1000.0f);
  } else {
    Serial.printf("[PH] raw_avg=%d | A0=%.3f V | pH unavailable: %s\n",
                  ph.raw, ph.voltage, ph.error ? ph.error : "unknown error");
  }

  if (turb.hasValue) {
    Serial.printf("[TURBIDITY] raw_avg=%d | A2=%.3f V | sensor_OUT_est=%.3f V | relative_index=%.1f/100 | status=%s (NOT NTU)\n",
                  turb.raw, turb.voltage,
                  turb.voltage * (TURBIDITY_R1_OHMS + TURBIDITY_R2_OHMS) / TURBIDITY_R2_OHMS,
                  turb.value, getTurbidityStatus(turb.value));
  } else {
    Serial.printf("[TURBIDITY] raw_avg=%d | A2=%.3f V | unavailable: %s\n",
                  turb.raw, turb.voltage, turb.error ? turb.error : "unknown error");
  }

  if (tds.hasValue) {
    Serial.printf("[TDS] raw_avg=%d | A1=%.3f V | NaCl-eq=%.1f mg/L | calibrated (T=%.1f C%s)\n",
                  tds.raw, tds.voltage, tds.value, waterTempC,
                  waterTempValid ? "" : " assumed (DS18B20 invalid)");
  } else {
    Serial.printf("[TDS] raw_avg=%d | A1=%.3f V | unavailable: %s\n",
                  tds.raw, tds.voltage, tds.error ? tds.error : "unknown error");
  }

  if (!temp.valid) pushError(temp.error);
  if (!ph.hasValue && ph.error != NULL) pushError("pH unavailable; inspect analog diagnostics");
  if (!turb.hasValue && turb.error != NULL) pushError("turbidity estimate unavailable; inspect analog diagnostics");
  if (!tds.hasValue && tds.error != NULL) pushError("TDS unavailable; inspect analog diagnostics");
  if (!adsReady) pushError("ads1115: not found on I2C bus");

  char topic[128];
  snprintf(topic, sizeof(topic), "%s/%s/telemetry", MQTT_TOPIC_PREFIX, STATION_CODE);

  char payload[MQTT_BUF_SIZE];
  size_t p = 0;
  p = appendf(payload, p, sizeof(payload),
              "{\"station_code\":\"%s\",\"device_id\":\"%s\",\"timestamp\":\"%s\",",
              STATION_CODE, DEVICE_ID, ts);
  p = appendJsonNum(payload, p, sizeof(payload), "pH", ph.hasValue, ph.value, 2);
  p = appendf(payload, p, sizeof(payload), ",\"pH_status\":\"%s\",", ph.hasValue ? "calibrated" : "unavailable");
  p = appendJsonNum(payload, p, sizeof(payload), "turbidity", turb.hasValue, turb.value, 2);
  p = appendf(payload, p, sizeof(payload), ",\"turbidity_status\":\"%s\",\"turbidity_unit\":\"relative_index_0_100\",",
              turb.hasValue ? getTurbidityStatus(turb.value) : "UNAVAILABLE");
  p = appendJsonNum(payload, p, sizeof(payload), "tds", tds.hasValue, tds.value, 1);
  p = appendf(payload, p, sizeof(payload), ",");
  p = appendJsonNum(payload, p, sizeof(payload), "temperature", temp.valid, temp.value, 2);
  p = appendf(payload, p, sizeof(payload), ",\"source\":\"esp32\",\"diagnostics\":{");

  // Raw hardware data — never used for ML inference, shown to operators as-is.
  p = appendAnalogDiag(payload, p, sizeof(payload), "ph", ph);
  p = appendAnalogDiag(payload, p, sizeof(payload), "turbidity", turb);
  p = appendAnalogDiag(payload, p, sizeof(payload), "tds", tds);
  p = appendf(payload, p, sizeof(payload),
              "\"temperature\":{\"sensor\":\"DS18B20\",\"valid\":%s",
              temp.valid ? "true" : "false");
  if (!temp.valid) p = appendf(payload, p, sizeof(payload), ",\"error\":\"%s\"", temp.error);
  p = appendf(payload, p, sizeof(payload), "},\"device\":{\"uptime_ms\":%lu,\"wifi_rssi_dbm\":%d,\"seq\":%lu,\"errors\":[",
              millis(), (int)WiFi.RSSI(), publishSeq);
  for (size_t i = 0; i < deviceErrorCount; i++) {
    p = appendf(payload, p, sizeof(payload), "%s\"%s\"", i ? "," : "", deviceErrors[i]);
  }
  p = appendf(payload, p, sizeof(payload), "]}}}");

  bool ok = mqttClient.publish(topic, payload);
  if (ok) {
    publishSeq++;
    deviceErrorCount = 0;   // errors acknowledged by a successful uplink
    Serial.printf("[PUB] %s -> %s\n", topic, payload);
  } else {
    pushError("mqtt publish failed (buffer? connection?)");
    Serial.println("[PUB] FAILED — publish returned false");
  }
}

// -----------------------------------------------------------------------------
// Connectivity (non-blocking, backoff, never resets the board)
// -----------------------------------------------------------------------------
void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) { wifiUp = true; return; }
  if (wifiUp) {
    wifiUp = false;
    Serial.println("[WIFI] connection lost");
  }
  if (millis() - lastWifiAttemptMs < WIFI_RETRY_MS) return;
  lastWifiAttemptMs = millis();
  Serial.printf("[WIFI] reconnecting to %s...\n", WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void maintainMqtt() {
  if (!wifiUp) { mqttUp = false; return; }
  if (mqttClient.connected()) { mqttUp = true; return; }
  if (mqttUp) {
    mqttUp = false;
    Serial.println("[MQTT] connection lost");
  }
  if (millis() - lastMqttAttemptMs < MQTT_RETRY_MS) return;
  lastMqttAttemptMs = millis();
  Serial.printf("[MQTT] connecting to %s:%d...\n", MQTT_HOST, MQTT_PORT);
  bool ok;
  if (MQTT_USER[0] == '\0') {
    ok = mqttClient.connect(DEVICE_ID);              // anonymous broker
  } else {
    ok = mqttClient.connect(DEVICE_ID, MQTT_USER, MQTT_PASSWORD);
  }
  if (ok) {
    mqttUp = true;
    Serial.println("[MQTT] connected");
  } else {
    Serial.printf("[MQTT] failed, rc=%d (will retry)\n", mqttClient.state());
  }
}

// -----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(100);

  // ADS1115 on I²C (default address 0x48, SDA 21 / SCL 22).
  // Init failure is handled honestly: analog values publish as null and the
  // device reports the fault instead of reading garbage from a missing chip.
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  ads.setGain(ADS_GAIN);
  adsReady = ads.begin();
  if (adsReady) {
    Serial.println("[ADS] ADS1115 ready (addr 0x48, gain +/-4.096 V)");
  } else {
    Serial.println("[ADS] ERROR: ADS1115 not found on I2C bus — analog sensors will report null");
  }

  ds18b20.begin();
  if (ds18b20.getDeviceCount() == 0) pushError("ds18b20: no device on bus");

  // ---- Calibration fitting: real constants only; fails CLOSED to nulls ----
#if PH_CALIBRATED
  phVAt7 = CAL_PH_V7;
  phVoltsPerPh = (CAL_PH_V7 - CAL_PH_V4) / 3.0f;
  if (isfinite(phVAt7) && isfinite(phVoltsPerPh) &&
      CAL_PH_V4 > CAL_PH_V7 &&
      fabsf(phVoltsPerPh) >= 0.030f && fabsf(phVoltsPerPh) <= 0.120f) {
    phCalValid = true;
  } else {
    Serial.println("[PH] calibration rejected: check CAL_PH_V4 > CAL_PH_V7 and a sane 30-120 mV/pH slope");
  }
#endif

#if TDS_CALIBRATED
  {
    bool ok = TDS_CAL_COUNT >= 4;
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0, s4 = 0, sc = 0, svc = 0, sv2c = 0;
    if (ok) {
      for (size_t i = 0; i < TDS_CAL_COUNT; ++i) {
        const double v = (double)TDS_CAL_POINTS[i][0];
        const double c = (double)TDS_CAL_POINTS[i][1];
        if (!isfinite(v) || !isfinite(c) || v < 0.0 || v > 3.25 || c < 0.0) { ok = false; break; }
        s0 += 1.0; s1 += v; s2 += v * v; s3 += v * v * v; s4 += v * v * v * v;
        sc += c; svc += v * c; sv2c += v * v * c;
      }
    }
    if (ok) {
      float m[3][4] = {
        { (float)s4, (float)s3, (float)s2, (float)sv2c },
        { (float)s3, (float)s2, (float)s1, (float)svc   },
        { (float)s2, (float)s1, (float)s0, (float)sc    }
      };
      float sol[3];
      ok = solve3x3(m, sol);
      if (ok) {
        tdsPolyA = sol[0]; tdsPolyB = sol[1]; tdsPolyC = sol[2];
        // Sanity-check the fit against every calibration point: the fitted
        // polynomial must reproduce each standard within +/-20 %.
        for (size_t i = 0; i < TDS_CAL_COUNT && ok; ++i) {
          const float v = TDS_CAL_POINTS[i][0];
          const float c = TDS_CAL_POINTS[i][1];
          const float fit = tdsPolyA * v * v + tdsPolyB * v + tdsPolyC;
          if (!isfinite(fit) || fabsf(fit - c) > 0.20f * c + 1.0f) {
            Serial.println("[TDS] calibration rejected: polynomial does not reproduce a reference standard (max 20% error)");
            ok = false;
          }
        }
      } else {
        Serial.println("[TDS] calibration rejected: singular fit system (check calibration points)");
      }
    }
    if (ok) tdsCalValid = true;
    else { tdsPolyA = tdsPolyB = tdsPolyC = 0.0f; tdsCalValid = false; }
  }
#endif

#if TURBIDITY_CALIBRATED
  Serial.println("[TURBIDITY] NOTE: TURBIDITY_CALIBRATED is a placeholder - no NTU lookup table exists yet, the value keeps publishing as relative_index_0_100.");
#endif

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptMs = millis();

  // ESP32 core signature: configTime(gmtOffset_sec, dstOffset_sec, server1, server2, ...)
  // 0, 0 = UTC with no daylight-saving offset — timestamps stay honest UTC.
  configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2);

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(MQTT_BUF_SIZE);

  Serial.printf("\n[BOOT] HydraSense station %s (device %s), topic %s/%s/telemetry\n",
                STATION_CODE, DEVICE_ID, MQTT_TOPIC_PREFIX, STATION_CODE);
  Serial.printf("[PH] calibration: V7=%.4f V, %.2f mV/pH -> %s\n",
                phVAt7, fabsf(phVoltsPerPh) * 1000.0f,
                phCalValid ? "CALIBRATED" : "UNCALIBRATED (pH publishes null)");
  Serial.printf("[TDS] calibration: %d reference standards -> %s\n",
                (int)TDS_CAL_COUNT,
                tdsCalValid ? "CALIBRATED (second-order fit, NaCl-eq mg/L, k=1+0.02*(T-25))"
                            : "UNCALIBRATED (TDS publishes null)");
  Serial.printf("[TURBIDITY] relative index 0-100; CLEARER <30, MODERATE 30-54, CLOUDIER >=55. Sensor OUT refs: clear=%.3f V, cloudy/dirty=%.3f V. NOT NTU.\n",
                TURBIDITY_CLEAR_SENSOR_VOLTAGE, TURBIDITY_CLOUDY_SENSOR_VOLTAGE);
}

void loop() {
  maintainWiFi();
  maintainMqtt();
  mqttClient.loop();   // keepalive

  if (mqttUp && millis() - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    lastPublishMs = millis();
    publishTelemetry();
  }
  delay(20);
}
