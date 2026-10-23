// =============================================================================
// HydraSense ESP32 Station — firmware
//
// Publishes one JSON telemetry packet per cycle to:
//     hydrasense/stations/<STATION_CODE>/telemetry
// which the HydraSense backend (MQTT subscriber) ingests into sensor_readings.
//
// DEMO MODE: pH and TDS are voltage-based estimates. Turbidity is a LIVE
// averaged reading from ADS1115 A2, published as a PROVISIONAL RELATIVE INDEX
// (0-100, higher = cloudier) anchored to two sample-based reference voltages —
// it is NOT NTU and NOT laboratory-calibrated. Raw ADC counts and voltages
// remain in diagnostics. A disconnected DS18B20 still publishes null rather
// than a fabricated temperature.
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

// ---- Provisional turbidity relative index (A2 live read) ------------------
// Wiring: sensor OUT -> 10 kΩ -> A2 junction, A2 junction -> 20 kΩ -> GND,
// so the sensor's output voltage is recovered as  A2 voltage × 1.5.
// (Keep the divider: the 5 V sensor output must NEVER reach the ADS1115 directly.)
//
// The 0-100 index below maps between two PROVISIONAL SAMPLE-BASED reference
// voltages measured from this build's sensor — they are NOT a laboratory
// calibration and the index is deliberately NEVER labelled NTU:
//   clear-water sensor output ≈ 0.354 V  -> index 0
//   cloudy-water sensor output ≈ 0.273 V  -> index 100
#define TURB_NUM_SAMPLES       10                 // averaged samples per reading
#define TURB_SAMPLE_GAP_MS     20                 // spacing between samples
#define TURB_DIVIDER_RATIO     1.5f               // sensor OUT = A2 volts × 1.5
#define TURB_REF_CLEAR_V       0.354f             // provisional clear-water reference
#define TURB_REF_CLOUDY_V      0.273f             // provisional cloudy-water reference
// Provisional status bands on the relative index:
//   CLEARER < 30 <= MODERATE < 55 <= CLOUDIER
#define TURB_STATUS_CLEARER_MAX  30
#define TURB_STATUS_MODERATE_MAX 55

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
  float voltage;
  bool calibrated;     // retained for compatibility; demo values are not calibrated
  bool hasValue;       // a demo estimate is available when ADS1115 is present
  float value;
};

struct TempResult {
  bool valid;
  float value;
  const char* error;   // NULL when valid
};

// Live turbidity read: averaged A2 counts, junction voltage, estimated sensor
// output voltage, and the provisional 0-100 relative index + status band.
struct TurbidityReading {
  bool valid;            // false = no honest index (publishes null, never 0)
  int  rawAvg;           // averaged raw ADC counts over TURB_NUM_SAMPLES
  float a2Voltage;       // A2 junction voltage (V)
  float sensorVoltage;   // estimated sensor output voltage (A2 × 1.5)
  float index;           // provisional relative index 0-100 (higher = cloudier)
  const char* status;    // "CLEARER" | "MODERATE" | "CLOUDIER" ("UNKNOWN" when invalid)
  const char* error;     // NULL when valid, else why the index is absent
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

// DEMO pH estimate: anchored to the user's observed pH-7 buffer voltage.
// This theoretical-slope estimate is not a substitute for probe calibration.
AnalogResult readPh() {
  AnalogResult r;
  r.raw = adsReadCounts(CH_PH);
  r.voltage = countsToVolts((int16_t)r.raw);
  r.calibrated = false;
  r.hasValue = adsReady;
  r.value = 7.0f - ((r.voltage - 1.052f) / 0.05916f);
  if (r.value < 0.0f) r.value = 0.0f;
  if (r.value > 14.0f) r.value = 14.0f;
  if (!adsReady) { r.hasValue = false; r.value = 0.0f; }
  return r;
}

// Live turbidity read from ADS1115 A2 through the existing voltage divider.
// TURB_NUM_SAMPLES single-ended reads are averaged (~TURB_SAMPLE_GAP_MS apart)
// to tame noise, then converted to a PROVISIONAL RELATIVE INDEX 0-100 using the
// two sample-based reference voltages. This is NOT an NTU calibration: without
// laboratory standards only a relative, clearly-labelled index is honest.
// Missing ADS1115 -> valid=false (payload publishes null, never a fake 0).
TurbidityReading readTurbidity() {
  TurbidityReading r;
  r.valid = false;
  r.rawAvg = 0;
  r.a2Voltage = 0.0f;
  r.sensorVoltage = 0.0f;
  r.index = 0.0f;
  r.status = "UNKNOWN";
  r.error = NULL;

  if (!adsReady) { r.error = "ads1115 unavailable"; return r; }   // no ADC -> no reading

  long sum = 0;
  for (int i = 0; i < TURB_NUM_SAMPLES; i++) {
    sum += adsReadCounts(CH_TURBIDITY);
    if (i < TURB_NUM_SAMPLES - 1) delay(TURB_SAMPLE_GAP_MS);
  }
  r.rawAvg = (int)(sum / TURB_NUM_SAMPLES);
  r.a2Voltage = countsToVolts((int16_t)r.rawAvg);
  r.sensorVoltage = r.a2Voltage * TURB_DIVIDER_RATIO;

  // Relative index: clear ref -> 0, cloudy ref -> 100, linear in between,
  // clamped to [0, 100]. Division-by-zero guard: identical reference
  // voltages would make the scale meaningless — report invalid instead.
  const float span = TURB_REF_CLEAR_V - TURB_REF_CLOUDY_V;   // +0.081 V nominal
  if (span <= 0.0f) {
    // Misconfigured references (clear <= cloudy): refuse to index rather than
    // emit an inverted or NaN scale.
    r.error = "invalid reference voltages (clear <= cloudy)";
    pushError("turbidity: invalid reference voltages (clear <= cloudy)");
    return r;
  }
  float idx = ((TURB_REF_CLEAR_V - r.sensorVoltage) / span) * 100.0f;
  if (idx < 0.0f) idx = 0.0f;
  if (idx > 100.0f) idx = 100.0f;
  r.index = idx;

  if      (r.index <  TURB_STATUS_CLEARER_MAX)  r.status = "CLEARER";
  else if (r.index <  TURB_STATUS_MODERATE_MAX) r.status = "MODERATE";
  else                                          r.status = "CLOUDIER";

  r.valid = true;
  return r;
}

// DEMO TDS linear mapping based on two user-observed pairs:
// 0.628 V -> 329 ppm; 2.190 V -> 1970 ppm. Not validated outside these points.
float tdsConvert(float voltageV) {
  float ppm = (1050.58f * voltageV) - 330.76f;
  return ppm < 0.0f ? 0.0f : ppm;
}

AnalogResult readTds() {
  AnalogResult r;
  r.raw = adsReadCounts(CH_TDS);
  r.voltage = countsToVolts((int16_t)r.raw);
  r.calibrated = false;
  r.hasValue = adsReady;
  r.value = tdsConvert(r.voltage);
  if (!adsReady) { r.hasValue = false; r.value = 0.0f; }
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
  pos = appendf(buf, pos, cap,
                "\"%s\":{\"raw_adc\":%d,\"voltage_v\":%.3f,\"calibration_status\":\"%s\"",
                key, r.raw, r.voltage, r.hasValue ? "demo_estimate" : "pending");
  if (!adsReady) pos = appendf(buf, pos, cap, ",\"error\":\"ads1115 unavailable\"");
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
  TurbidityReading turb = readTurbidity();
  AnalogResult tds = readTds();
  TempResult temp = readTemperature();
  if (!temp.valid) pushError(temp.error);
  if (!adsReady) pushError("ads1115: not found on I2C bus");

  char topic[128];
  snprintf(topic, sizeof(topic), "%s/%s/telemetry", MQTT_TOPIC_PREFIX, STATION_CODE);

  char payload[MQTT_BUF_SIZE];
  size_t p = 0;
  p = appendf(payload, p, sizeof(payload),
              "{\"station_code\":\"%s\",\"device_id\":\"%s\",\"timestamp\":\"%s\",",
              STATION_CODE, DEVICE_ID, ts);
  p = appendJsonNum(payload, p, sizeof(payload), "pH", ph.hasValue, ph.value, 2);
  p = appendf(payload, p, sizeof(payload), ",");
  // `turbidity` keeps its legacy field name for MQTT/DB compatibility, but on
  // hardware it carries the PROVISIONAL RELATIVE INDEX (0-100, higher =
  // cloudier) — NOT NTU. The unit lives in diagnostics (relative_index_0_100).
  p = appendJsonNum(payload, p, sizeof(payload), "turbidity", turb.valid, turb.index, 1);
  p = appendf(payload, p, sizeof(payload), ",");
  p = appendJsonNum(payload, p, sizeof(payload), "tds", tds.hasValue, tds.value, 1);
  p = appendf(payload, p, sizeof(payload), ",");
  p = appendJsonNum(payload, p, sizeof(payload), "temperature", temp.valid, temp.value, 2);
  p = appendf(payload, p, sizeof(payload), ",\"source\":\"esp32\",\"diagnostics\":{");

  // Raw hardware data — never used for ML inference, shown to operators as-is.
  p = appendAnalogDiag(payload, p, sizeof(payload), "ph", ph);
  // Turbidity diagnostics: averaged counts, A2 junction voltage, reconstructed
  // sensor voltage, relative index + status band, and the unit metadata that
  // keeps the index from ever being misread as NTU.
  p = appendf(payload, p, sizeof(payload),
              "\"turbidity\":{\"unit\":\"relative_index_0_100\",\"raw_adc\":%d,\"voltage_v\":%.3f,\"sensor_output_v\":%.3f,",
              turb.rawAvg, turb.a2Voltage, turb.sensorVoltage);
  if (turb.valid) {
    p = appendf(payload, p, sizeof(payload),
                "\"relative_index\":%.1f,\"relative_status\":\"%s\",\"calibration_status\":\"provisional_index\"",
                turb.index, turb.status);
  } else {
    p = appendf(payload, p, sizeof(payload),
                "\"relative_index\":null,\"relative_status\":null,\"calibration_status\":\"pending\",\"error\":\"%s\"",
                turb.error ? turb.error : "unknown");
  }
  p = appendf(payload, p, sizeof(payload), "},");
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
