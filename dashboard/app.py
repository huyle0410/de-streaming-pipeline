import time

import pandas as pd
import psycopg2
import streamlit as st

PG_CONN = dict(host="postgres", dbname="iot", user="pipeline", password="pipeline", port=5432)

st.set_page_config(page_title="IoT Streaming Pipeline", layout="wide")
st.title("Real-Time IoT Sensor Pipeline")
st.caption("Kafka -> Spark Structured Streaming -> Postgres -> Airflow batch rollup")


def query(sql):
    conn = psycopg2.connect(**PG_CONN)
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


placeholder = st.empty()

while True:
    with placeholder.container():
        col1, col2, col3 = st.columns(3)

        total = query("SELECT count(*) AS n FROM sensor_readings")["n"].iloc[0]
        last = query("SELECT max(ingested_at) AS t FROM sensor_readings")["t"].iloc[0]
        locations = query("SELECT count(DISTINCT location) AS n FROM sensor_readings")["n"].iloc[0]

        col1.metric("Total readings ingested", f"{total:,}")
        col2.metric("Distinct locations", locations)
        col3.metric("Last ingested at (UTC)", str(last))

        st.subheader("Latest raw readings")
        st.dataframe(
            query("SELECT sensor_id, location, event_time, temperature_c, humidity_pct FROM sensor_readings ORDER BY event_time DESC LIMIT 20"),
            use_container_width=True,
        )

        st.subheader("Rolling 1-minute window stats per location (Spark aggregation)")
        window_df = query(
            "SELECT location, window_start, window_end, avg_temperature_c, max_temperature_c, avg_humidity_pct, reading_count "
            "FROM sensor_window_stats ORDER BY window_start DESC LIMIT 50"
        )
        st.dataframe(window_df, use_container_width=True)

        if not window_df.empty:
            chart_df = window_df.pivot_table(
                index="window_start", columns="location", values="avg_temperature_c", aggfunc="mean"
            ).sort_index()
            st.line_chart(chart_df)

        st.subheader("Daily rollup (Airflow batch job)")
        st.dataframe(query("SELECT * FROM daily_rollup ORDER BY rollup_date DESC, location LIMIT 50"), use_container_width=True)

    time.sleep(5)
