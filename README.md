# Real-Time IoT Streaming Pipeline

A self-hosted, containerized data pipeline demonstrating Kafka, Spark Structured
Streaming, Airflow, and Postgres working together end to end.

## Why this project

This is a personal project built to get hands-on with the core streaming data
stack most Data Engineer roles expect: a message broker (Kafka), a stream
processing engine (Spark Structured Streaming), and a batch orchestrator
(Airflow) — wired together into one pipeline instead of studied in isolation.

The use case (simulated IoT sensors reporting temperature/humidity) is
intentionally simple so the focus stays on the data engineering patterns that
transfer to any real streaming system:

- **Decoupling ingestion from processing** via Kafka, so the producer and the
  consumer can fail or scale independently.
- **Event-time vs. processing-time**, windowed aggregation, and watermarking
  in Spark Structured Streaming — the concepts that make streaming different
  from a batch job run more often.
- **Streaming + batch working together**: Spark handles the continuous
  aggregation; Airflow handles the scheduled rollups and pipeline health
  checks that streaming alone isn't suited for.
- **Multiple consumption layers from one store**: the same Postgres tables
  serve a live Streamlit dashboard and a Power BI report, showing the data
  is usable beyond the pipeline itself.

Everything runs self-hosted via Docker Compose (Kubernetes migration planned
as a next step), so the whole stack — producer, Kafka, Spark, Postgres,
Airflow, dashboard — is inspectable and runnable on a single machine.

## Architecture

```
[Python producer]  -->  [Kafka]  -->  [Spark Structured Streaming]  -->  [Postgres]
  (simulates 7          topic:           - raw events                       |
   IoT sensors,        sensor-readings    - 1-min windowed stats             |
   1 msg / 1-2s)                                                            |
                                                                              v
                        [Airflow] -- batch rollup + freshness check -->  daily_rollup
                                                                              |
                                                                              v
                                            [Streamlit dashboard]  /  [Power BI]
```

| Stage | Component | What it does |
|---|---|---|
| Ingest | `producer/sensor_producer.py` | Simulates 7 IoT sensors (4 locations: warehouse-A, warehouse-B, cold-storage, office) sending temperature/humidity JSON events to Kafka every 1-2s |
| Transport | Kafka (KRaft mode, no Zookeeper) | Buffers/distributes events on topic `sensor-readings`, keyed by `sensor_id` |
| Process | `spark/jobs/stream_processor.py` | Reads from Kafka, writes raw events to `sensor_readings`, computes a 1-minute sliding window aggregation (avg/max temp, avg humidity, count per location) into `sensor_window_stats` |
| Orchestrate (batch) | `airflow/dags/iot_rollup_dag.py` | Every 5 min: checks pipeline freshness, then rolls up `sensor_readings` into a daily summary table `daily_rollup` |
| Serve | Postgres (`iot` database) | Final storage layer — 3 tables at 3 levels of granularity (raw / windowed / daily) |
| Visualize | Streamlit dashboard, or Power BI | Reads directly from Postgres for a live view |

## Data contract

Each Kafka message (and row in `sensor_readings`) looks like:

```json
{
  "sensor_id": "sensor-05",
  "location": "cold-storage",
  "timestamp": "2026-10-12T10:23:45+00:00",
  "temperature_c": 3.8,
  "humidity_pct": 81.4
}
```

## Running it

```bash
docker compose up -d --build
```

Services and ports:

| Service | URL | Notes |
|---|---|---|
| Kafka UI | http://localhost:8081 | Inspect topics/messages |
| Kafka broker | localhost:9092 | For external clients |
| Postgres | localhost:5433 | db=`iot`, user=`pipeline`, password=`pipeline` |
| Spark job | (no UI, runs `local[2]` inside `spark-submit` container) | Logs: `docker compose logs -f spark-submit` |
| Airflow webserver | http://localhost:8082 | login `admin` / `admin` |
| Streamlit dashboard | http://localhost:8501 | Auto-refreshing live view |

Check things are flowing:

```bash
docker compose logs -f producer       # see simulated sensor events being sent
docker compose logs -f spark-submit   # see Spark batches being processed
docker exec -it iot-postgres psql -U pipeline -d iot -c "select count(*) from sensor_readings;"
```

## Connecting Power BI (refreshable dashboard)

Two options, both already in `dashboard/`:

### Option A — ready-made report (recommended for the demo)

`dashboard/IoTPipeline/` (also zipped as `dashboard/IoTPipeline.zip`) is a
Power BI **project (PBIP)** — an Overview page (KPI cards, a line chart of
avg temperature per location, a live table of recent readings) and a Daily
Rollup page, already wired to query Postgres directly (Import mode, table
`sensor_readings` / `sensor_window_stats` / `daily_rollup`).
`dashboard/IoTPipeline.pbix` is a compiled export of that report (opens
directly in Power BI Desktop, no need to Extract All a zip first) —
regenerate it from the PBIP any time with **File > Save As** after a Refresh.

1. Copy the `IoTPipeline` folder (or unzip `IoTPipeline.zip`), or just copy
   `IoTPipeline.pbix` directly, to your Windows machine and open it.
2. Power BI Desktop opens the report; the first time, it will ask you to
   select authentication for the PostgreSQL source — enter user `pipeline`,
   password `pipeline`. Requires the Npgsql driver (Power BI prompts to
   install it if missing) and `localhost:5433` reachable from Windows (WSL2
   forwards this automatically; otherwise use the WSL IP from `hostname -I`).
3. Click **Refresh** to pull the latest rows.

This was generated by `dashboard/build_pbip.py` by hand-assembling the PBIP
file format (JSON + TMDL), not by running Power BI Desktop itself. It's been
opened and verified working in Power BI Desktop, including live data from
Postgres on the Overview and Daily Rollup pages. Uses the IFAD Corporate
color theme for styling (no logo/branding — this is a personal project).

If you edit `build_pbip.py` and regenerate, two gotchas already hit once:
- Extract the zip fully before opening `.pbip` (double-clicking it straight
  out of File Explorer's zip preview leaves the sibling `.Report` /
  `.SemanticModel` folders behind and Desktop reports a missing artifact).
- In the M query, `PostgreSQL.Database(...){[Schema="public",Item="..."]}`
  must use the actual lowercase Postgres table name (`sensor_readings`, not
  `SensorReadings`) and include `Kind="Table"` in the key, or you'll get
  "The key didn't match any rows in the table".
- `dashboard/IoTPipeline.pbix` lives one level above the `IoTPipeline/`
  folder on purpose — `rm -rf IoTPipeline && python3 build_pbip.py` (the
  normal way to regenerate) wipes that folder, and anything saved inside it
  (like a `.pbix` export) goes with it.

### Option B — connect your own report

`dashboard/iot_pipeline.pbids` is a connection shortcut: double-click it and
Power BI Desktop opens **Get Data** pre-filled with the Postgres server
(`localhost:5433`), database (`iot`) and **DirectQuery** mode, so you build
your own visuals from a guaranteed-working connection. Pick from
`sensor_readings`, `sensor_window_stats`, `daily_rollup`; credentials are the
same as above. With DirectQuery, visuals re-query Postgres on every
interaction/refresh instead of caching a snapshot.

Note: scheduled automatic refresh in the Power BI **Service** (cloud) would need
an on-premises data gateway, since this Postgres instance only runs locally in
Docker. For a local demo, Power BI Desktop + manual refresh is enough.

## Project layout

```
de-streaming-pipeline/
├── docker-compose.yml
├── postgres/init.sql          # creates airflow db + iot tables
├── producer/                  # simulated sensor -> Kafka
├── spark/jobs/                # Structured Streaming job
├── airflow/dags/               # batch rollup + freshness check DAG
└── dashboard/                  # Streamlit live view
```
