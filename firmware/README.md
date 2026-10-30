# HydraSense ESP32 Station — setup & testing guide

Physical water-quality station firmware for HydraSense. Data flow:

```
ESP32 --Wi-Fi--> MQTT broker (Mosquitto, your PC) --> FastAPI backend --> PostgreSQL
     topic: hydrasense/stations/<station_code>/telemetry   (validate+ML)   (sensor_readings)
```

## Honesty contract (firmware + backend enforce it together)

- An **uncalibrated** sensor publishes JSON `null` for its engineering value
  (pH/NaCl-equivalent mg/L). Raw ADC counts + voltage go into `diagnostics`
  instead. `diagnostics.<sensor>.calibration_status` is `"uncalibrated"`.
- Calibration flags **gate the published values**: `PH_CALIBRATED` and
  `TDS_CALIBRATED` in `config.h` control whether pH/TDS publish an engineering
  value at all. The firmware re-checks the calibration constants at boot and
  refuses an implausible fit (slope outside 30–120 mV/pH, or a TDS polynomial
  that does not reproduce a reference standard within ±20%) — the sensor then
  stays `null` with the rejection logged on Serial.
- **Turbidity is the exception**: it is a live averaged read from ADS1115 A2
  published as a **provisional relative index 0–100** (higher = cloudier),
  anchored to two sample-based reference voltages — **not NTU**, not a
  laboratory calibration. The unit is explicit in the payload field
  `"turbidity_unit":"relative_index_0_100"`. If the ADC is missing the value
  is `null`, never a fabricated 0. `TURBIDITY_CALIBRATED` is a **placeholder**
  (no NTU conversion exists yet); setting it changes nothing but a boot notice.
- A **failed** sensor (e.g. DS18B20 unplugged) publishes `null` + `valid:false`.
  Never 0, never a guess.
- Every packet carries `"source":"esp32"` so hardware rows stay distinguishable
  from simulator rows (which default to `source="simulator"`).
- No publishing until NTP time is synced — timestamps are always honest UTC.

## 1. Hardware & wiring

| Part | Connection |
|---|---|
| ESP32 DevKit V1 | any classic WROOM board |
| ADS1115 ADC | SDA -> GPIO **21**, SCL -> GPIO **22**, VDD 3.3 V, GND common (addr 0x48) |
| Analog pH module | out -> ADS1115 **A0**, GND common |
| Analog TDS module | "A" out -> ADS1115 **A1** |
| Analog turbidity module | out -> **existing two-resistor voltage divider** -> ADS1115 **A2** |
| DS18B20 temperature | DATA -> GPIO **4** + **4.7 k pull-up** to 3.3 V |

No sensor connects to the ESP32's own ADC pins (GPIO 32/34/35 are unused).

**Input voltage safety (ADS1115 powered at 3.3 V):**

- Absolute maximum input is **VDD + 0.3 V ≈ 3.6 V**. The gain setting does
  NOT make a higher voltage safe — it only changes the measurement range
  (the firmware uses ±4.096 V full-scale).
- Your turbidity module measured **~3.5–3.72 V** at its output. It must reach
  A2 only through the divider. **Before first power-up, measure the divider
  output with a multimeter** (sensor in air): it must read **≤ 3.3 V**.
- If it can exceed 3.3 V, do not power the board — increase the divider ratio
  (two equal resistors, e.g. 10k/10k, halve it to ~1.75–1.86 V) and
  re-measure. Do not raise the sensor supply voltage.
- pH (typically 0–3.3 V) and TDS (typically 0–2.4 V) fit the range, but
  verify each once with a multimeter before trusting readings.
- Keep the existing common-ground arrangement.

## 2. Arduino toolchain

1. Arduino IDE 2.x + **esp32** board core (Boards Manager -> "esp32" by Espressif).
2. Library Manager -> install **PubSubClient** (Nick O'Leary),
   **OneWire** (Paul Stoffregen), **DallasTemperature** (Miles Burton),
   **Adafruit ADS1X15** (Adafruit — ADS1115 driver; pulls in Adafruit BusIO
   automatically).
3. Board: e.g. "ESP32 Dev Module", upload speed 115200.

## 3. Secrets — never committed

```
firmware/hydrasense_esp32/config.example.h   (template, committed)
firmware/hydrasense_esp32/config.h           (YOUR values, gitignored)
```

Copy the template to `config.h` in the same folder and fill in Wi-Fi SSID,
password, broker IP, station code, device id. `config.h` is in `.gitignore` —
do not rename or force-add it to git. Keep all calibration flags at 0 until
you have done real reference calibration (see section 10).

> **Wi-Fi credentials note:** `config.h` holds the real SSID/password and is
> never committed. Do not paste it into issues, screenshots or documentation.

## 4. MQTT broker on your PC (Mosquitto)

1. Install from <https://mosquitto.org/download/> (check "install as service").
2. Edit `C:\Program Files\mosquitto\mosquitto.conf` so a LAN device may connect:

   ```
   listener 1883
   allow_anonymous true
   ```

   (Mosquitto 2.x blocks anonymous LAN clients by default; the two lines above
   are required for first-time testing.)
3. Restart the service (admin terminal): `net stop mosquitto && net start mosquitto`
4. Allow the port through Windows Firewall (admin terminal):

   ```
   netsh advfirewall firewall add rule name="Mosquitto1883" dir=in action=allow protocol=TCP localport=1883
   ```

5. Get your PC's LAN address: `ipconfig` -> "IPv4 Address" (e.g. 192.168.1.10).
   Put that in `MQTT_HOST` in `config.h` — not `localhost`, not `127.0.0.1`.
6. ESP32 uses 2.4 GHz Wi-Fi only — the PC and the ESP32 must be on the same
   network (AP isolation off, if your router has it).

## 5. Backend

```bash
cd backend
cp .env.example .env        # then edit DATABASE_URL / secrets
pip install -r requirements.txt
alembic upgrade head         # adds source + diagnostics columns
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Do **not** use `python run_server.py` (it fails without an import string).
The default broker settings (`localhost:1883`, topic prefix
`hydrasense/stations`) already match this firmware — only set
`MQTT_BROKER_HOST` if the backend runs on a different machine than the broker.
Seed stations if the DB is empty: `python scripts/seed_demo.py` (station codes
`ARK-001`, `ARK-002`, `ARK-003`). Unknown station codes are rejected.

## 6. Compile, upload & watch

1. Open `hydrasense_esp32/hydrasense_esp32.ino` in Arduino IDE 2.x
   (`config.h` must sit in the same folder — the sketch includes it).
2. Select **Tools > Board > ESP32 Arduino > ESP32 Dev Module** and the COM
   port of your board.
3. Click **Verify** (✓) — a missing library or `config.h` fails here first.
4. Click **Upload** (→); hold the **BOOT** button if the upload stalls.
5. Open **Tools > Serial Monitor** at **115200** baud.

Healthy boot and publish cycle:

```
[BOOT] HydraSense station ARK-001 (device ESP32-HS-001), topic hydrasense/stations/ARK-001/telemetry
[ADS] ADS1115 ready (addr 0x48, gain +/-4.096 V)
[WIFI] reconnecting to <ssid>...          (only if needed)
[MQTT] connecting to 192.168.1.10:1883...
[MQTT] connected
[PUB] hydrasense/stations/ARK-001/telemetry -> {"station_code":"ARK-001",...}
```

If the ADC chip is missing you get
`[ADS] ERROR: ADS1115 not found on I2C bus — analog sensors will report null`:
packets keep flowing with null pH/TDS/turbidity and the fault listed in
`device.errors` — honest, not broken.

`[TIME] NTP not synced yet — deferring publish` is normal for the first few
seconds after boot; publishing starts automatically once time is valid.

**Simple test procedure**

1. Serial shows `[ADS] ... ready`, `[MQTT] connected`, then `[PUB] ...` lines.
2. In another terminal: `mosquitto_sub -h localhost -t "hydrasense/stations/#" -v`
   — one line should arrive every ~3 s.
3. Change an input (pH probe into buffer, DS18B20 into warm water): within a
   few packets the printed `diagnostics.ph.voltage_v` / `temperature` change.
4. Backend log shows `Ingested SensorReading id=... source='esp32'`, and the
   dashboard card (section 9) shows "Physical hardware (ESP32)" + Online.

## 7. Test the pipeline WITHOUT hardware

Watch the topic from the PC (any machine with mosquitto clients):

```
mosquitto_sub -h localhost -t "hydrasense/stations/#" -v
```

Simulator-style full payload:

```
mosquitto_pub -h localhost -t "hydrasense/stations/ARK-001/telemetry" ^
  m "{\"station_code\":\"ARK-001\",\"device_id\":\"STATION-ARK-001\",\"timestamp\":\"2026-10-22T10:15:30Z\",\"pH\":7.1,\"turbidity\":4.0,\"tds\":200.0,\"temperature\":25.0}"
```ESP32-style uncalibrated payload (NULLs + raw diagnostics):

```
mosquitto_pub -h localhost -t "hydrasense/stations/ARK-001/telemetry" ^
  m "{\"station_code\":\"ARK-001\",\"device_id\":\"ESP32-HS-001\",\"timestamp\":\"2026-10-22T10:15:33Z\",\"pH\":null,\"pH_status\":\"unavailable\",\"turbidity\":61.7,\"turbidity_status\":\"CLOUDIER\",\"turbidity_unit\":\"relative_index_0_100\",\"tds\":null,\"temperature\":27.0,\"source\":\"esp32\",\"diagnostics\":{\"ph\":{\"raw_adc\":19952,\"voltage_v\":2.494,\"valid\":false,\"calibration_status\":\"uncalibrated\",\"error\":\"pH uncalibrated: set PH_CALIBRATED=1 with CAL_PH_V7/CAL_PH_V4 buffer voltages (firmware/README.md section 10)\"},\"turbidity\":{\"raw_adc\":8431,\"voltage_v\":1.054,\"valid\":true,\"calibration_status\":\"provisional_estimate\",\"sensor_output_v\":1.581,\"value_type\":\"relative_index_0_100\",\"classification\":\"CLOUDIER\"},\"tds\":{\"raw_adc\":32,\"voltage_v\":0.004,\"valid\":false,\"calibration_status\":\"uncalibrated\"},\"temperature\":{\"sensor\":\"DS18B20\",\"valid\":true},\"device\":{\"uptime_ms\":69112,\"wifi_rssi_dbm\":-41,\"seq\":0,\"errors\":[]}}}```

(On cmd.exe use one line without `^`; on bash keep the backslash continuations.)
Backend log should show `Ingested SensorReading id=... source='esp32'`.

## 8. Verify in PostgreSQL

```sql
SELECT sr.id, ms.station_code, sr.device_id, sr.timestamp,
       sr.ph, sr.turbidity, sr.tds, sr.temperature, sr.source
FROM sensor_readings sr
JOIN monitoring_stations ms ON ms.id = sr.station_id
ORDER BY sr.id DESC LIMIT 5;

SELECT id, device_id, diagnostics
FROM sensor_readings WHERE source = 'esp32'
ORDER BY id DESC LIMIT 1;
```

Expected: hardware rows show `source='esp32'` with NULL cells for uncalibrated
sensors and a populated `diagnostics` JSON; simulator rows show
`source='simulator'`, NULL diagnostics.

## 9. Verify on the dashboard

1. `cd frontend && npm install && npm run dev` (port 5173),
   `frontend/.env` pointing `VITE_API_BASE_URL` at the backend if non-default.
2. Log in as an authority account (demo: `authority@hydrasense.local` /
   `DemoAuthority123!`).
3. Open **Live IoT Sensor Monitoring**, pick the station in the backend-station
   selector. The **Station Telemetry** card shows:
   - link badge Online (< 15 s old) / Stale (< 5 min) / Offline (older);
   - provenance badge "Physical hardware (ESP32)" vs "Simulated";
   - "Uncalibrated" / "Sensor failed" tiles instead of fabricated numbers;
   - the raw ADC / voltage / calibration table and device errors (RSSI,
     uptime, sequence number).

## 10. Calibration (do this before trusting any values)

All flags start at 0 in `config.h`: the station reports NULL engineering values
plus raw ADC/voltage — that is correct, not a bug. To calibrate:

1. **pH (two-point fit)** — measure the probe voltage at the ADS1115 input in
   a pH 7.00 buffer → `CAL_PH_V7`, then in a pH 4.01 buffer → `CAL_PH_V4`
   (must be higher than V7 for the common module whose voltage falls as pH
   rises). Set `PH_CALIBRATED 1`. The firmware computes the slope as
   `(CAL_PH_V7 − CAL_PH_V4)/3` at boot and rejects an implausible fit (outside
   30–120 mV/pH). Validate the fit with a buffer **not** used in it (e.g. pH
   9.18) before trusting readings. If a voltage divider sits on the pH line,
   the measured junction voltage already includes it — do not divide again.
   Optional: set `PH_TEMP_COMPENSATION 1` to apply the Nernst temperature
   term using the DS18B20 (must be recorded in `docs/FEATURE_STATUS.md`).
2. **Turbidity** — the station already publishes a live provisional relative
   index (0–100) from A2; it needs no calibration to show *relative* clarity
   changes. `TURBIDITY_CALIBRATED` is a **placeholder**: no NTU conversion is
   implemented. A future NTU upgrade must use a piecewise lookup built from
   formazin / reference-meter standards (0, 20, 100, 800 NTU), measured
   through the divider, with interpolation — never a single straight line,
   and never a conversion of the existing index value. Until then the index
   must never be read or labelled as NTU.
3. **TDS (≥4 standard fit)** — prepare NaCl reference standards (e.g. 0, 250,
   500, 1000, 2000 mg/L), immerse the probe, and record the voltage the
   Serial monitor prints on ADS1115 A1 for each. In `config.h` define BOTH:

   ```c
   const size_t TDS_CAL_COUNT = 4;
   const float  TDS_CAL_POINTS[][2] = { {voltage_v, mg_per_l}, ... };
   ```

   then set `TDS_CALIBRATED 1`. Note: constants named `TDS_CAL_V0` / `TDS_CAL_V250`
   mentioned in earlier revisions of this document **do not exist** — the
   sketch has never used them; the list above is the real contract. The
   firmware fits a least-squares second-order polynomial through the points,
   verifies each point within ±20%, and compensates the measured voltage to
   25 °C with `k = 1 + 0.02·(T−25)` using the DS18B20 (when the DS18B20 is
   invalid it assumes 25 °C and logs `assumed (DS18B20 invalid)`). Published
   values are **NaCl-equivalent conductivity in mg/L** — a screening input,
   not dissolved-solids mass.
4. Reflash. The dashboard tiles switch from "Uncalibrated" to values and the
   calibration column shows `calibrated`. Once ALL FOUR values exist (incl.
   temperature), the backend also runs ML inference on each reading.
5. **Record every recalibration** in `docs/FEATURE_STATUS.md` with the date,
   constants and who measured them — recalibration shifts screening results
   and the ML feature distribution relative to the models' training data.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Wi-Fi never connects | 5 GHz-only SSID, wrong password | use a 2.4 GHz SSID |
| `[MQTT] failed, rc=...` | broker down, wrong IP/port, firewall | test with `mosquitto_sub` on the PC first; re-run firewall rule; check `MQTT_HOST` is the PC's LAN IPv4 |
| `[PUB] FAILED` | connection dropped between keepalives | watch for `[MQTT] connection lost`; check AP signal / power |
| Publish deferred forever by `[TIME]` | NTP blocked (UDP 123 outbound) | allow outbound UDP 123 or change NTP servers in `config.h` |
| Backend log: unknown station_code | code not in DB | use `ARK-001..003` or seed/insert the station |
| Backend log: `Skipped duplicate` | QoS redelivery / retransmit of the same timestamp | normal — the duplicate guard working |
| Backend log: nothing at all | subscriber not connected | confirm `pip install -r requirements.txt` (needs `paho-mqtt>=2.0`); broker must be reachable from the backend host |
| Dashboard says "No data" | no readings yet, or signed in as non-authority | publish a test payload; log in with an authority account |
| Device drops every few minutes | another device uses the same `DEVICE_ID` (MQTT client id collision) | make `DEVICE_ID` unique per station |
| Temperature always NULL | DS18B20 wiring / missing 4.7 k pull-up | check DATA to GPIO 4 + pull-up; card shows the fault text |
| `[ADS] ERROR: ADS1115 not found` | I²C wiring, missing common GND | SDA->GPIO 21, SCL->GPIO 22, shared GND; most modules answer at 0x48 |
| Analog values NULL despite `[ADS] ... ready` | calibration flags at 0 in `config.h` | expected until calibrated (section 10); the `calibration_status` diag says `uncalibrated`, `device.errors` explains |
| Boot log: `[PH] calibration rejected` | implausible constants | check `CAL_PH_V4 > CAL_PH_V7`, fresh buffers, and a 30–120 mV/pH slope |
| Boot log: `[TDS] calibration rejected...` | bad or singular calibration points | re-measure the standards; `TDS_CAL_COUNT >= 4`, all voltages 0–3.25 V |

Automated regression tests for the ingestion contract live in
`backend/tests/test_telemetry.py` (NULL handling, provenance, diagnostics,
duplicate guard, role access): `cd backend && python -m pytest tests/test_telemetry.py -v`.
