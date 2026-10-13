from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

PG_CONN = dict(host="postgres", dbname="iot", user="pipeline", password="pipeline", port=5432)


def run_daily_rollup():
    import psycopg2

    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO daily_rollup
            (rollup_date, location, avg_temperature_c, max_temperature_c, avg_humidity_pct, reading_count)
        SELECT
            event_time::date AS rollup_date,
            location,
            AVG(temperature_c) AS avg_temperature_c,
            MAX(temperature_c) AS max_temperature_c,
            AVG(humidity_pct) AS avg_humidity_pct,
            COUNT(*) AS reading_count
        FROM sensor_readings
        WHERE event_time >= now() - interval '1 day'
        GROUP BY event_time::date, location
        ON CONFLICT (rollup_date, location)
        DO UPDATE SET
            avg_temperature_c = EXCLUDED.avg_temperature_c,
            max_temperature_c = EXCLUDED.max_temperature_c,
            avg_humidity_pct = EXCLUDED.avg_humidity_pct,
            reading_count = EXCLUDED.reading_count,
            computed_at = now()
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def check_pipeline_freshness():
    import psycopg2

    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    cur.execute("SELECT max(ingested_at) FROM sensor_readings")
    last_ingested = cur.fetchone()[0]
    cur.close()
    conn.close()

    if last_ingested is None:
        raise ValueError("No data has been ingested yet — producer/Spark job may not be running")

    age_seconds = (datetime.utcnow() - last_ingested).total_seconds()
    print(f"[freshness-check] last ingested row is {age_seconds:.0f}s old")
    if age_seconds > 120:
        raise ValueError(f"Pipeline looks stale: last row ingested {age_seconds:.0f}s ago")


default_args = {
    "owner": "data-eng",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="iot_rollup_and_health",
    description="Batch rollup of streaming IoT data + pipeline freshness check",
    default_args=default_args,
    schedule_interval=timedelta(minutes=5),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["iot", "rollup", "demo"],
) as dag:

    check_freshness = PythonOperator(
        task_id="check_pipeline_freshness",
        python_callable=check_pipeline_freshness,
    )

    daily_rollup = PythonOperator(
        task_id="run_daily_rollup",
        python_callable=run_daily_rollup,
    )

    check_freshness >> daily_rollup
