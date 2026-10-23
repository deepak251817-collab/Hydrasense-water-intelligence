import json
import logging
import re
from datetime import datetime, timezone
from typing import Tuple, Optional, Any, Dict
import paho.mqtt.client as mqtt

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.water import MonitoringStation, SensorReading
from app.services.ml_service import (
    MLServiceUnavailableError,
    MLValidationError,
    ml_service,
)

logger = logging.getLogger("hydrasense.mqtt")

# Provenance tag for physical station hardware; anything else defaults to
# "simulator" (Python simulator, seeded rows predating this field).
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")

# Cap on the serialized diagnostics blob (raw ADC + voltages + device health).
# Keeps a misbehaving device from bloating rows; real payloads are ~500 bytes.
DIAGNOSTICS_MAX_CHARS = 8192

# ---- Turbidity unit contract -------------------------------------------------
# ESP32 hardware publishes a PROVISIONAL RELATIVE INDEX 0-100 (higher =
# cloudier) which is NOT NTU. The simulator publishes NTU-style values. The
# unit travels either as a top-level `turbidity_unit` field or inside
# `diagnostics.turbidity.unit` (current firmware). Rows with no unit are
# stored with turbidity_unit=NULL (unknown) — never silently treated as NTU
# or as a relative index.
TURBIDITY_UNIT_RELATIVE = "relative_index_0_100"
TURBIDITY_UNIT_NTU = "ntu"
TURBIDITY_UNIT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
TURBIDITY_STATUS_BANDS = ("CLEARER", "MODERATE", "CLOUDIER")


def parse_turbidity_meta(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract and validate the turbidity unit/status for a payload.

    Sources, in order: top-level `turbidity_unit` / `turbidity_status`, then
    `diagnostics.turbidity.unit` / `diagnostics.turbidity.relative_status`
    (the shape the current ESP32 firmware emits).

    Returns (unit, status, error). `unit`/`status` are None when absent;
    `error` is a human-readable reason when the fields are malformed.
    A status band is only meaningful for relative-index readings.
    """
    unit = data.get("turbidity_unit")
    status = data.get("turbidity_status")

    diagnostics = data.get("diagnostics")
    diag_turbidity = None
    if isinstance(diagnostics, dict):
        candidate = diagnostics.get("turbidity")
        if isinstance(candidate, dict):
            diag_turbidity = candidate

    if unit is None and diag_turbidity is not None:
        unit = diag_turbidity.get("unit")
    if status is None and diag_turbidity is not None:
        status = diag_turbidity.get("relative_status")

    if unit is not None:
        if not isinstance(unit, str) or not TURBIDITY_UNIT_PATTERN.match(unit):
            return None, None, f"Invalid turbidity_unit (1-32 chars [A-Za-z0-9_.-]): {unit!r}"
        unit = unit.strip()

    if status is not None:
        if not isinstance(status, str):
            return None, None, f"Invalid turbidity_status: {status!r}"
        status = status.strip().upper()
        if status not in TURBIDITY_STATUS_BANDS:
            return None, None, (
                "Invalid turbidity_status (expected CLEARER, MODERATE or CLOUDIER): "
                f"{status!r}"
            )

    # A status band only describes a relative-index reading. A missing value
    # has neither unit nor status; a non-relative unit (e.g. NTU) keeps its
    # unit but drops the band.
    if data.get("turbidity") is None:
        return None, None, None
    if unit != TURBIDITY_UNIT_RELATIVE:
        status = None

    return unit, status, None


def parse_timestamp(ts_str: Any) -> Optional[datetime]:
    if not isinstance(ts_str, str):
        return None
    # A date alone ("2026-10-25") is valid ISO-8601 but not a telemetry
    # timestamp: every reading would collapse onto midnight and look like a
    # duplicate. Require a time component.
    if "T" not in ts_str and " " not in ts_str:
        return None
    try:
        # Handle ISO-8601 string (e.g. '2026-08-31T23:00:00Z' or with offset)
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1] + '+00:00'
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def validate_telemetry_payload(data: Dict[str, Any]) -> Tuple[bool, str]:
    required_fields = ["station_code", "device_id", "timestamp", "pH", "turbidity", "tds", "temperature"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    station_code = data.get("station_code")
    if not isinstance(station_code, str) or not station_code.strip():
        return False, "Invalid or empty station_code"

    device_id = data.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        return False, "Invalid or empty device_id"

    ts = parse_timestamp(data.get("timestamp"))
    if ts is None:
        return False, "Invalid timestamp format (ISO-8601 required)"

    # A sensor value may be JSON null: the device has NO honest measurement
    # for it (uncalibrated analog sensor, or a failed/missing sensor). NULL is
    # stored as NULL — never fabricated, never interpreted as "safe". Numeric
    # values must still pass the exact physical range checks as before.
    # Turbidity unit/status (optional, but must be well-formed when present).
    turbidity_unit, _turbidity_status, turbidity_error = parse_turbidity_meta(data)
    if turbidity_error:
        return False, turbidity_error

    # NOTE on `turbidity`: simulator payloads carry NTU-like values; ESP32
    # hardware payloads carry a PROVISIONAL RELATIVE INDEX 0-100 (higher =
    # cloudier, never NTU). The unit is stored per row, so consumers must check
    # `turbidity_unit` before interpreting the number. A relative index is
    # additionally bounded to [0, 100]; NTU-style values keep the >= 0 range.
    sensor_ranges: Dict[str, Tuple[float, float]] = {
        "pH": (0.0, 14.0),
        "turbidity": (0.0, float("inf")),
        "tds": (0.0, float("inf")),
        "temperature": (-20.0, 70.0),
    }
    for field, (lo, hi) in sensor_ranges.items():
        value = data[field]
        if value is None:
            continue
        # JSON booleans are not measurements (bool is an int subclass, so
        # float(True) would otherwise be accepted as 1.0).
        if isinstance(value, bool):
            return False, f"Non-numeric value provided for {field}"
        try:
            numeric = float(value)
        except (ValueError, TypeError):
            return False, f"Non-numeric value provided for {field}"
        if not (lo <= numeric <= hi):
            return False, f"{field} out of valid physical range [{lo}, {hi}]: {numeric}"
        if field == "turbidity" and turbidity_unit == TURBIDITY_UNIT_RELATIVE and numeric > 100.0:
            return False, f"turbidity relative index out of range [0, 100]: {numeric}"

    # Optional provenance tag: "esp32" for physical hardware, "simulator" for
    # the Python simulator. Anything absent or invalid becomes "simulator".
    source = data.get("source")
    if source is not None and (
        not isinstance(source, str) or not SOURCE_PATTERN.match(source)
    ):
        return False, f"Invalid source tag (1-20 chars [A-Za-z0-9_-]): {source!r}"

    # Optional device diagnostics (raw ADC, voltages, calibration status,
    # device health). Stored verbatim, size-capped.
    diagnostics = data.get("diagnostics")
    if diagnostics is not None:
        if not isinstance(diagnostics, dict):
            return False, "diagnostics must be a JSON object"
        try:
            if len(json.dumps(diagnostics)) > DIAGNOSTICS_MAX_CHARS:
                return False, f"diagnostics blob exceeds {DIAGNOSTICS_MAX_CHARS} characters"
        except (TypeError, ValueError):
            return False, "diagnostics is not JSON-serializable"

    return True, "Valid"


def attach_ml_results(reading_id: int, ph: float, turbidity: float,
                      tds: float, temperature: float,
                      db_session_factory=SessionLocal) -> bool:
    """Run ML inference for a stored reading and persist the results.

    Failure policy (Phase 6 section 6): ML problems NEVER break telemetry
    ingestion — the reading is already committed. On any ML failure the
    reading keeps NULL ML fields (no fabricated prediction is stored) and the
    error is logged.
    """
    db = db_session_factory()
    try:
        if not ml_service.is_available:
            # Attempt a lazy (re)load once; a missing artifact keeps ML off.
            ml_service.load_models()
        if not ml_service.is_available:
            logger.warning(
                "ML service unavailable; SensorReading id=%s stored without ML results.",
                reading_id,
            )
            return False
        try:
            result = ml_service.predict(ph=ph, turbidity=turbidity, tds=tds, temperature=temperature)
        except MLValidationError as err:
            logger.warning("Invalid ML input for SensorReading id=%s: %s", reading_id, err)
            return False
        except MLServiceUnavailableError as err:
            logger.warning("ML inference unavailable for SensorReading id=%s: %s", reading_id, err)
            return False
        except Exception as err:
            logger.error("ML inference failed for SensorReading id=%s: %s", reading_id, err, exc_info=True)
            return False

        reading = db.query(SensorReading).filter(SensorReading.id == reading_id).first()
        if reading is None:
            logger.warning("SensorReading id=%s vanished before ML results could be stored.", reading_id)
            return False
        reading.anomaly_label = result.anomaly_label
        reading.anomaly_score = result.anomaly_score
        reading.water_quality_label = result.water_quality_label
        reading.safe_probability = result.safe_probability
        reading.unsafe_probability = result.unsafe_probability
        reading.ml_processed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("ML results stored for SensorReading id=%s", reading_id)
        return True
    except Exception as err:
        db.rollback()
        logger.error("Error storing ML results for SensorReading id=%s: %s", reading_id, err, exc_info=True)
        return False
    finally:
        db.close()


def process_telemetry_payload(payload_str: str, db_session_factory=SessionLocal) -> bool:
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError as err:
        logger.error(f"Failed to parse MQTT message JSON payload: {err}")
        return False

    if not isinstance(data, dict):
        logger.error("MQTT message JSON payload must be a JSON object")
        return False

    is_valid, reason = validate_telemetry_payload(data)
    if not is_valid:
        logger.warning(f"Rejected telemetry payload: {reason}")
        return False

    station_code = data["station_code"]
    device_id = data["device_id"]
    parsed_ts = parse_timestamp(data["timestamp"])
    turbidity_unit, turbidity_status, _ = parse_turbidity_meta(data)
    db = db_session_factory()
    try:
        station = db.query(MonitoringStation).filter(MonitoringStation.station_code == station_code).first()
        if not station:
            logger.warning(f"Rejected telemetry for unknown station_code: '{station_code}'")
            return False

        # Duplicate guard: MQTT QoS 1 redelivery or a device retransmit re-sends
        # the SAME timestamp (device clock is the source of truth per reading).
        # An exact (device_id, timestamp) match already stored is skipped.
        duplicate = (
            db.query(SensorReading.id)
            .filter(
                SensorReading.station_id == station.id,
                SensorReading.device_id == device_id,
                SensorReading.timestamp == parsed_ts,
            )
            .first()
        )
        if duplicate is not None:
            logger.info(
                f"Skipped duplicate telemetry for station='{station_code}' "
                f"device_id='{device_id}' timestamp={parsed_ts.isoformat()} "
                f"(existing SensorReading id={duplicate.id})"
            )
            return True

        reading = SensorReading(
            station_id=station.id,
            device_id=device_id,
            timestamp=parsed_ts,
            ph=None if data["pH"] is None else float(data["pH"]),
            turbidity=None if data["turbidity"] is None else float(data["turbidity"]),
            tds=None if data["tds"] is None else float(data["tds"]),
            temperature=None if data["temperature"] is None else float(data["temperature"]),
            # Unit only exists alongside a value; NULL = unknown, never NTU.
            turbidity_unit=turbidity_unit if data["turbidity"] is not None else None,
            turbidity_status=turbidity_status if data["turbidity"] is not None else None,
            source=data.get("source") or "simulator",
            diagnostics=data.get("diagnostics"),
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)
        logger.info(
            f"Ingested SensorReading id={reading.id} for station='{station_code}' "
            f"source='{reading.source}' (pH={reading.ph}, turbidity={reading.turbidity}, "
            f"unit={reading.turbidity_unit}, status={reading.turbidity_status}, "
            f"tds={reading.tds}, temp={reading.temperature})"
        )

        # ML honesty: the models were trained on NTU-style turbidity. A relative
        # index 0-100 is a different quantity, so feeding it to the model would
        # silently misread the feature — such readings keep NULL ML fields.
        if reading.turbidity_unit == TURBIDITY_UNIT_RELATIVE:
            logger.info(
                "SensorReading id=%s stored without ML results: turbidity is a "
                "relative index 0-100 (not NTU), so it cannot be used as an NTU model input.",
                reading.id,
            )
            return True

        # Phase 6: ML inference AFTER the reading is safely persisted — and only
        # when ALL four sensor values exist. A reading with any NULL value
        # (uncalibrated or failed sensor) keeps NULL ML fields: no prediction is
        # ever fabricated from missing data.
        if None in (reading.ph, reading.turbidity, reading.tds, reading.temperature):
            logger.info(
                "SensorReading id=%s stored without ML results: one or more sensor "
                "values are NULL (uncalibrated or failed sensor).",
                reading.id,
            )
            return True

        attach_ml_results(
            reading_id=reading.id,
            ph=reading.ph,
            turbidity=reading.turbidity,
            tds=reading.tds,
            temperature=reading.temperature,
            db_session_factory=db_session_factory,
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error persisting SensorReading to database: {e}", exc_info=True)
        return False
    finally:
        db.close()


class MQTTSubscriberService:
    def __init__(
        self,
        host: str = settings.MQTT_BROKER_HOST,
        port: int = settings.MQTT_BROKER_PORT,
        topic_prefix: str = settings.MQTT_TOPIC_PREFIX,
        db_session_factory=SessionLocal
    ):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix.rstrip("/")
        self.topic = f"{self.topic_prefix}/+/telemetry"
        self.db_session_factory = db_session_factory
        self.is_connected = False

        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        else:
            self.client = mqtt.Client()

        self._setup_callbacks()

    def _setup_callbacks(self):
        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                self.is_connected = True
                logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
                client.subscribe(self.topic, qos=1)
                logger.info(f"Subscribed to topic pattern: {self.topic}")
            else:
                self.is_connected = False
                logger.error(f"MQTT connection failed with return code {rc}")

        def on_disconnect(client, userdata, flags, rc=None, properties=None):
            self.is_connected = False
            logger.warning(f"Disconnected from MQTT broker (rc={rc})")

        def on_message(client, userdata, msg):
            try:
                payload_str = msg.payload.decode("utf-8")
                logger.debug(f"Received MQTT msg on topic {msg.topic}: {payload_str}")
                process_telemetry_payload(payload_str, db_session_factory=self.db_session_factory)
            except Exception as err:
                logger.error(f"Error handling MQTT message on topic {msg.topic}: {err}", exc_info=True)

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message

    def start(self):
        logger.info(f"Starting MQTT subscriber service towards {self.host}:{self.port}...")
        try:
            self.client.connect_async(self.host, self.port, keepalive=60)
            self.client.loop_start()
            logger.info("MQTT background loop started.")
        except Exception as err:
            logger.error(f"Failed to initialize MQTT broker connection: {err}. App will remain active.")

    def stop(self):
        logger.info("Stopping MQTT subscriber service...")
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT subscriber service stopped cleanly.")
        except Exception as err:
            logger.error(f"Error shutting down MQTT client: {err}")


# Global service instance
mqtt_service = MQTTSubscriberService()
