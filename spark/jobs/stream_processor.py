import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, max as spark_max, avg, count, window
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "sensor-readings")
PG_URL = os.environ.get("PG_URL", "jdbc:postgresql://postgres:5432/iot")
PG_USER = os.environ.get("PG_USER", "pipeline")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "pipeline")

SCHEMA = StructType([
    StructField("sensor_id", StringType()),
    StructField("location", StringType()),
    StructField("timestamp", TimestampType()),
    StructField("temperature_c", DoubleType()),
    StructField("humidity_pct", DoubleType()),
])

PG_PROPERTIES = {
    "user": PG_USER,
    "password": PG_PASSWORD,
    "driver": "org.postgresql.Driver",
}


def write_raw_batch(batch_df, batch_id):
    if batch_df.rdd.isEmpty():
        return
    (
        batch_df.select(
            col("sensor_id"), col("location"), col("timestamp").alias("event_time"),
            col("temperature_c"), col("humidity_pct"),
        )
        .write.jdbc(url=PG_URL, table="sensor_readings", mode="append", properties=PG_PROPERTIES)
    )


def upsert_window_batch(batch_df, batch_id):
    if batch_df.rdd.isEmpty():
        return

    rows = batch_df.collect()
    import psycopg2

    conn = psycopg2.connect(
        host="postgres", dbname="iot", user=PG_USER, password=PG_PASSWORD, port=5432,
    )
    cur = conn.cursor()
    for row in rows:
        cur.execute(
            """
            INSERT INTO sensor_window_stats
                (location, window_start, window_end, avg_temperature_c, max_temperature_c, avg_humidity_pct, reading_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (location, window_start)
            DO UPDATE SET
                window_end = EXCLUDED.window_end,
                avg_temperature_c = EXCLUDED.avg_temperature_c,
                max_temperature_c = EXCLUDED.max_temperature_c,
                avg_humidity_pct = EXCLUDED.avg_humidity_pct,
                reading_count = EXCLUDED.reading_count
            """,
            (
                row["location"], row["window"]["start"], row["window"]["end"],
                row["avg_temperature_c"], row["max_temperature_c"], row["avg_humidity_pct"], row["reading_count"],
            ),
        )
    conn.commit()
    cur.close()
    conn.close()


def main():
    spark = (
        SparkSession.builder.appName("iot-stream-processor")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .load()
    )

    parsed = (
        raw.select(from_json(col("value").cast("string"), SCHEMA).alias("data"))
        .select("data.*")
        .withWatermark("timestamp", "30 seconds")
    )

    raw_query = (
        parsed.writeStream.foreachBatch(write_raw_batch)
        .option("checkpointLocation", "/tmp/checkpoints/raw")
        .trigger(processingTime="5 seconds")
        .start()
    )

    windowed = (
        parsed.groupBy(window(col("timestamp"), "1 minute", "30 seconds"), col("location"))
        .agg(
            avg("temperature_c").alias("avg_temperature_c"),
            spark_max("temperature_c").alias("max_temperature_c"),
            avg("humidity_pct").alias("avg_humidity_pct"),
            count("*").alias("reading_count"),
        )
    )

    window_query = (
        windowed.writeStream.foreachBatch(upsert_window_batch)
        .outputMode("update")
        .option("checkpointLocation", "/tmp/checkpoints/windowed")
        .trigger(processingTime="10 seconds")
        .start()
    )

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
