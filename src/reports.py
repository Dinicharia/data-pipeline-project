# src/reports.py
# Generates daily summary reports after each pipeline run.
# In production these are emailed to stakeholders or
# published to a dashboard (Metabase, Superset, Grafana).

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime       import date
from src.database   import get_db_cursor
from src.logger     import get_logger
from src.config     import LOG_DIR

logger = get_logger(__name__)


def generate_daily_report() -> str:
    """
    Generate a daily summary report and save it to the logs folder.

    Returns:
        Report content as a formatted string
    """
    today = date.today().isoformat()

    with get_db_cursor(commit=False) as cursor:

        # ── Weather summary ───────────────────────────────────────────────
        cursor.execute("""
            SELECT
                c.name                              AS city,
                COUNT(*)                            AS readings,
                ROUND(AVG(wr.temperature_c), 2)     AS avg_temp,
                MIN(wr.temperature_c)               AS min_temp,
                MAX(wr.temperature_c)               AS max_temp,
                ROUND(AVG(wr.humidity_pct), 1)      AS avg_humidity
            FROM weather_readings wr
            JOIN cities c ON wr.city_id = c.id
            WHERE DATE(wr.recorded_at) = CURRENT_DATE
            GROUP BY c.name
            ORDER BY avg_temp DESC
        """)
        weather_rows = cursor.fetchall()

        # ── Exchange rate summary ─────────────────────────────────────────
        cursor.execute("""
            SELECT
                target_currency     AS currency,
                rate
            FROM exchange_rates
            WHERE DATE(recorded_at) = CURRENT_DATE
            ORDER BY target_currency
        """)
        rate_rows = cursor.fetchall()

        # ── Pipeline run summary ──────────────────────────────────────────
        cursor.execute("""
            SELECT
                COUNT(*)                        AS total_runs,
                SUM(CASE WHEN status = 'success'
                    THEN 1 ELSE 0 END)          AS successful,
                SUM(records_loaded)             AS total_records
            FROM pipeline_runs
            WHERE DATE(started_at) = CURRENT_DATE
        """)
        run_summary = cursor.fetchone()

    # ── Build report ──────────────────────────────────────────────────────
    lines = [
        f"{'='*60}",
        f"DAILY PIPELINE REPORT — {today}",
        f"{'='*60}",
        "",
        "PIPELINE RUNS:",
        f"  Total runs today : {run_summary['total_runs']}",
        f"  Successful       : {run_summary['successful']}",
        f"  Records loaded   : {run_summary['total_records']:,}",
        "",
        "WEATHER SUMMARY:",
        f"  {'City':<12} {'Readings':>8} {'Avg°C':>7} "
        f"{'Min°C':>7} {'Max°C':>7} {'Humidity':>9}",
        f"  {'-'*55}",
    ]

    for row in weather_rows:
        lines.append(
            f"  {row['city']:<12} {row['readings']:>8} "
            f"{row['avg_temp']:>7} {row['min_temp']:>7} "
            f"{row['max_temp']:>7} {row['avg_humidity']:>8}%"
        )

    lines += [
        "",
        "EXCHANGE RATES (USD base):",
    ]

    for row in rate_rows:
        lines.append(f"  1 USD = {row['rate']:>12.4f} {row['currency']}")

    lines += ["", f"{'='*60}"]
    report = "\n".join(lines)

    # Save report to logs folder
    report_file = LOG_DIR / f"report_{today}.txt"
    with open(report_file, "w") as f:
        f.write(report)

    logger.info(f"Daily report saved to {report_file}")
    return report


if __name__ == "__main__":
    print(generate_daily_report())