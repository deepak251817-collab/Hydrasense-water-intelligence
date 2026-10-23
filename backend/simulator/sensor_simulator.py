import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

STATIONS = [
    {"station_code": "ARK-001", "device_id": "STATION-ARK-001"},
    {"station_code": "ARK-002", "device_id": "STATION-ARK-002"},
    {"station_code": "ARK-003", "device_id": "STATION-ARK-003"},
]

SCENARIOS = ["normal", "deteriorating", "sudden_event", "sensor_fault"]


class SensorSimulator:
    def __init__(self, broker: str = "localhost", port: int = 1883, scenario: str = "normal"):
        self.broker = broker
        self.port = port
        self.scenario = scenario
        self.step_counter = 0

        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        else:
            self.client = mqtt.Client()

    def connect(self):
        print(f"[*] Connecting simulator to MQTT broker at {self.broker}:{self.port}...")
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            print("[+] Simulator connected successfully.")
        except Exception as e:
            print(f"[!] Failed to connect to MQTT broker: {e}")
            raise e

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("[*] Simulator disconnected cleanly.")

    def generate_reading(self, station_code: str, device_id: str) -> dict:
        self.step_counter += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.scenario == "normal":
            ph = round(7.0 + random.uniform(-0.3, 0.4), 2)
            turbidity = round(3.0 + random.uniform(0.0, 5.0), 2)
            tds = round(210.0 + random.uniform(-15.0, 25.0), 1)
            temperature = round(26.5 + random.uniform(-1.0, 1.5), 1)

        elif self.scenario == "deteriorating":
            # Gradual increase in turbidity & TDS, slight shift in pH
            drift = min(self.step_counter * 0.8, 30.0)
            ph = round(7.2 - min(self.step_counter * 0.05, 1.2) + random.uniform(-0.1, 0.1), 2)
            turbidity = round(10.0 + drift * 1.5 + random.uniform(-1.0, 2.0), 2)
            tds = round(300.0 + drift * 12.0 + random.uniform(-10.0, 10.0), 1)
            temperature = round(27.0 + random.uniform(-0.5, 0.5), 1)

        elif self.scenario == "sudden_event":
            # Sharp contamination spike
            ph = round(5.4 + random.uniform(-0.2, 0.2), 2)
            turbidity = round(78.5 + random.uniform(-5.0, 10.0), 2)
            tds = round(1150.0 + random.uniform(-40.0, 60.0), 1)
            temperature = round(29.2 + random.uniform(-0.8, 0.8), 1)

        elif self.scenario == "sensor_fault":
            # Out of bounds / invalid physical parameter
            fault_type = self.step_counter % 4
            if fault_type == 0:
                ph = 16.5  # Invalid pH > 14
                turbidity = 5.2
                tds = 220.0
                temperature = 25.0
            elif fault_type == 1:
                ph = 7.1
                turbidity = -15.0  # Invalid negative turbidity
                tds = 220.0
                temperature = 25.0
            elif fault_type == 2:
                ph = 7.1
                turbidity = 5.2
                tds = -50.0  # Invalid negative TDS
                temperature = 25.0
            else:
                ph = 7.1
                turbidity = 5.2
                tds = 220.0
                temperature = 120.0  # Invalid high temp

        else:
            # Default fallback
            ph = 7.0
            turbidity = 5.0
            tds = 200.0
            temperature = 25.0

        return {
            "station_code": station_code,
            "device_id": device_id,
            "timestamp": now_iso,
            "pH": ph,
            "turbidity": turbidity,
            # The simulator models NTU-style turbidity (unlike the ESP32's
            # relative index 0-100), so it states its unit explicitly.
            "turbidity_unit": "ntu",
            "tds": tds,
            "temperature": temperature,
        }

    def publish_cycle(self):
        for station in STATIONS:
            code = station["station_code"]
            dev_id = station["device_id"]
            reading = self.generate_reading(code, dev_id)
            topic = f"hydrasense/stations/{code}/telemetry"
            payload_str = json.dumps(reading)

            info = self.client.publish(topic, payload_str, qos=1)
            info.wait_for_publish(timeout=2.0)
            print(f"[PUB -> {topic}] Scenario={self.scenario} Payload={payload_str}")

    def run(self, interval: float = 5.0, count: int = 0):
        self.connect()
        cycles = 0
        try:
            print(f"[*] Starting telemetry publication loop (interval={interval}s, scenario={self.scenario})...")
            while True:
                self.publish_cycle()
                cycles += 1
                if count > 0 and cycles >= count:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[*] Stopping simulator loop via KeyboardInterrupt.")
        finally:
            self.disconnect()


def main():
    parser = argparse.ArgumentParser(description="HydraSense Phase 4 Python Sensor Simulator")
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT Broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker port (default: 1883)")
    parser.add_argument("--scenario", type=str, default="normal", choices=SCENARIOS, help="Simulation scenario")
    parser.add_argument("--interval", type=float, default=5.0, help="Publish interval in seconds (default: 5.0)")
    parser.add_argument("--count", type=int, default=0, help="Number of publish cycles to run (0 for infinite)")

    args = parser.parse_args()

    simulator = SensorSimulator(broker=args.broker, port=args.port, scenario=args.scenario)
    simulator.run(interval=args.interval, count=args.count)


if __name__ == "__main__":
    main()
