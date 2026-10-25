// =============================================================================
// HydraSense ESP32 Station — firmware
//
// Publishes one JSON telemetry packet per cycle to:
//     hydrasense/stations/<STATION_CODE>/telemetry
// which the HydraSense backend (MQTT subscriber) ingests into sensor_readings.
//
// DEMO MODE: pH and TDS are provisional estimates, not lab-calibrated values.
// Turbidity is a sensor-derived relative index (0-100), NOT NTU.
// Invalid pH estimates are sent as null rather than being clamped to zero.
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

// TEMPORARY pH offset requested for demo use.
// The previous reference (1.052 V) made the reported tap-water sample read 5.55.
// With the existing 59.16 mV/pH slope, 1.1378 V shifts that same sample to ~pH 7.
// This treats that tap-water voltage as pH 7 for display only; it is NOT a true
// calibration. Replace with the measured voltage of a correctly prepared pH 7
// calibration buffer, then perform multi-point calibration when possible.
const float PH_VOLTAGE_AT_PH7 = 1.0278f;
const float PH_VOLTS_PER_PH_UNIT = 0.05916f; // theoretical room-temperature slope

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

  const float estimate = 7.0f - ((r.voltage - PH_VOLTAGE_AT_PH7) / PH_VOLTS_PER_PH_UNIT);
  if (!isfinite(estimate) || estimate < 0.0f || estimate > 14.0f) {
    r.error = "pH estimate outside 0..14; check PH_VOLTAGE_AT_PH7 against a known pH 7 buffer";
    return r;
  }

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

// DEMO TDS linear mapping based on two user-observed pairs:
// 0.628 V -> 329 ppm; 2.190 V -> 1970 ppm. Not validated outside these points.
float tdsConvert(float voltageV) {
  float ppm = (1050.58f * voltageV) - 330.76f;
  return ppm < 0.0f ? 0.0f : ppm;
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
  r.value = tdsConvert(r.voltage);
  if (!isfinite(r.voltage) || r.voltage < 0.0f || r.voltage > 3.25f || !isfinite(r.value)) {
    r.error = "TDS voltage invalid; check sensor output and A1 wiring";
    return r;
  }
  r.hasValue = true;
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
  const char* calibrationStatus = r.hasValue ? "provisional_estimate" : "unavailable";
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

  AnalogResult ph = readPh();
  AnalogResult turb = readTurbidity();
  AnalogResult tds = readTds();

  if (ph.hasValue) {
    Serial.printf("[PH] raw_avg=%d | A0=%.3f V | provisional_pH=%.2f | NOT calibrated\n",
                  ph.raw, ph.voltage, ph.value);
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
    Serial.printf("[TDS] raw_avg=%d | A1=%.3f V | provisional_TDS=%.1f ppm | NOT calibrated\n",
                  tds.raw, tds.voltage, tds.value);
  } else {
    Serial.printf("[TDS] raw_avg=%d | A1=%.3f V | unavailable: %s\n",
                  tds.raw, tds.voltage, tds.error ? tds.error : "unknown error");
  }

  TempResult temp = readTemperature();
  if (!temp.valid) pushError(temp.error);
  if (!ph.hasValue && ph.error != NULL) pushError("pH estimate unavailable; inspect analog diagnostics");
  if (!turb.hasValue && turb.error != NULL) pushError("turbidity estimate unavailable; inspect analog diagnostics");
  if (!tds.hasValue && tds.error != NULL) pushError("TDS estimate unavailable; inspect analog diagnostics");
  if (!adsReady) pushError("ads1115: not found on I2C bus");

  char topic[128];
  snprintf(topic, sizeof(topic), "%s/%s/telemetry", MQTT_TOPIC_PREFIX, STATION_CODE);

  char payload[MQTT_BUF_SIZE];
  size_t p = 0;
  p = appendf(payload, p, sizeof(payload),
              "{\"station_code\":\"%s\",\"device_id\":\"%s\",\"timestamp\":\"%s\",",
              STATION_CODE, DEVICE_ID, ts);
  p = appendJsonNum(payload, p, sizeof(payload), "pH", ph.hasValue, ph.value, 2);
  p = appendf(payload, p, sizeof(payload), ",\"pH_status\":\"%s\",", ph.hasValue ? "provisional_estimate" : "unavailable");
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
  Serial.printf("[PH] TEMP demo offset reference: %.4f V at pH 7; theoretical slope %.5f V/pH. Not a verified calibration; use a proper pH 7 buffer for calibration.\n",
                PH_VOLTAGE_AT_PH7, PH_VOLTS_PER_PH_UNIT);
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
