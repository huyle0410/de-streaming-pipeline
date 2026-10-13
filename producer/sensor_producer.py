import json
import os
import random
import time
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TOPIC = os.environ.get("KAFKA_TOPIC", "sensor-readings")
MIN_INTERVAL_SEC = float(os.environ.get("MIN_INTERVAL_SEC", "1"))
MAX_INTERVAL_SEC = float(os.environ.get("MAX_INTERVAL_SEC", "2"))

SENSORS = [
    {"sensor_id": "sensor-01", "location": "warehouse-A", "base_temp": 22.0, "base_humidity": 55.0},
    {"sensor_id": "sensor-02", "location": "warehouse-A", "base_temp": 23.5, "base_humidity": 58.0},
    {"sensor_id": "sensor-03", "location": "warehouse-B", "base_temp": 19.0, "base_humidity": 62.0},
    {"sensor_id": "sensor-04", "location": "warehouse-B", "base_temp": 20.5, "base_humidity": 60.0},
    {"sensor_id": "sensor-05", "location": "cold-storage", "base_temp": 4.0, "base_humidity": 80.0},
    {"sensor_id": "sensor-06", "location": "cold-storage", "base_temp": 3.5, "base_humidity": 82.0},
    {"sensor_id": "sensor-07", "location": "office", "base_temp": 24.0, "base_humidity": 45.0},
]


def connect_with_retry():
    for attempt in range(1, 31):
        try:
            return KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8"),
            )
        except NoBrokersAvailable:
            print(f"[producer] Kafka not ready yet (attempt {attempt}), retrying in 2s...")
            time.sleep(2)
    raise RuntimeError("Could not connect to Kafka after 30 attempts")


def make_reading(sensor):
    now = datetime.now(timezone.utc)
    temp_noise = random.uniform(-1.5, 1.5)
    humidity_noise = random.uniform(-4.0, 4.0)

    temperature = round(sensor["base_temp"] + temp_noise, 2)
    humidity = round(max(0.0, min(100.0, sensor["base_humidity"] + humidity_noise)), 2)

    if random.random() < 0.02:
        temperature += random.choice([15, -10])

    return {
        "sensor_id": sensor["sensor_id"],
        "location": sensor["location"],
        "timestamp": now.isoformat(),
        "temperature_c": temperature,
        "humidity_pct": humidity,
    }


def main():
    producer = connect_with_retry()
    print(f"[producer] Connected to Kafka at {BOOTSTRAP_SERVERS}, publishing to topic '{TOPIC}'")

    while True:
        sensor = random.choice(SENSORS)
        reading = make_reading(sensor)
        producer.send(TOPIC, key=reading["sensor_id"], value=reading)
        print(f"[producer] sent: {reading}")
        time.sleep(random.uniform(MIN_INTERVAL_SEC, MAX_INTERVAL_SEC))


if __name__ == "__main__":
    main()
