# 🔁 Data Pipeline Project

> A production-quality, end-to-end ETL pipeline that collects live data from four public APIs, cleans and validates it with Pandas, loads it into PostgreSQL, and orchestrates everything automatically with Apache Airflow — fully containerised with Docker.

---

## 📌 Table of Contents

- [Overview](#overview)
- [Live Data Sources](#live-data-sources)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Key Engineering Concepts](#key-engineering-concepts)
- [Getting Started](#getting-started)
- [Running the Pipeline](#running-the-pipeline)
- [Running with Apache Airflow](#running-with-apache-airflow)
- [Running with Prefect](#running-with-prefect)
- [Database Schema](#database-schema)
- [Testing](#testing)
- [Design Decisions](#design-decisions)
- [What I Learned](#what-i-learned)

---

## Overview

This project was built as a complete, portfolio-ready demonstration of modern Data Engineering practices. It is not a toy example — it uses real APIs, handles real failures, validates real data, and follows the same patterns used in production data teams.

The pipeline runs daily on a schedule, extracts live data from four public APIs, cleans and transforms it, loads it into a relational database, and maintains a full audit trail of every run. If a source fails, the pipeline continues with the others and retries automatically. If bad data is detected, it is rejected before it ever reaches the database.

**What makes this production-quality:**

- **Idempotent loading** — running the pipeline ten times produces the same database state as running it once. `ON CONFLICT DO NOTHING` prevents duplicate records even on restarts.
- **Full audit trail** — every pipeline run is recorded in a `pipeline_runs` table with its status, record counts, duration, and any error messages.
- **Data quality gates** — data is validated against range constraints, null checks, and duplicate detection before loading. Bad data is rejected loudly, not silently ignored.
- **Graceful failure handling** — one API failing does not crash the pipeline. Each source is independent, failures are logged, and retries use exponential backoff.
- **Landing layer pattern** — raw API responses are saved to disk before any transformation. This enables replay without re-hitting the API, debugging without losing original data, and compliance auditing.

---

## Live Data Sources

| Source | API | What We Collect | Schedule |
|--------|-----|-----------------|----------|
| 🌤️ OpenWeatherMap | `/data/2.5/weather` | Temperature, humidity, pressure, wind, conditions for 5 cities | Daily |
| 💱 Open Exchange Rates | `/v6/latest/USD` | USD exchange rates for KES, GBP, EUR, JPY, AUD, CAD, CHF | Daily |
| 🐙 GitHub API | `/repos/{owner}/{repo}` | Stars, forks, open issues, activity for 4 major Python repos | Daily |
| 🔭 NASA APOD | `/planetary/apod` | Astronomy Picture of the Day metadata for the last 7 days | Daily |

**Monitored cities:** Nairobi · London · New York · Tokyo · Sydney

**Tracked repositories:** `python/cpython` · `pandas-dev/pandas` · `apache/airflow` · `psf/requests`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPLETE ETL PIPELINE                       │
│                                                                 │
│  EXTRACT               TRANSFORM              LOAD             │
│  ───────               ─────────              ────             │
│                                                                 │
│  weather_extractor  ──► weather_transformer  ──► PostgreSQL    │
│  exchange_extractor ──► rate_transformer     ──► PostgreSQL    │
│  github_extractor   ──► github_transformer   ──► (tracked)     │
│  nasa_extractor     ──► nasa_transformer     ──► (tracked)     │
│                                ↑                               │
│                         quality_gate                           │
│                    (validates before loading)                  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Apache Airflow  —  schedules and orchestrates all tasks  │ │
│  │  Parallel extraction → sequential transform/load          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Docker  —  containerises the entire stack                │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Airflow DAG — Task Dependency Graph

```
start
  │
  ├──► extract_weather ──► transform_weather ──► load_weather ──────┐
  ├──► extract_rates   ──► transform_rates   ──► load_rates   ──────┤
  ├──► extract_github  ──────────────────────────────────────────── │
  └──► extract_nasa    ──────────────────────────────────────────── │
                                                                     ▼
                                                          refresh_materialized_views
                                                                     │
                                                                    end
```

The four extractions run **in parallel** — Airflow handles the concurrency automatically because they have no dependency on each other. This is something a simple sequential script cannot do.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Language | Python 3.11 | Core pipeline code |
| Orchestration | Apache Airflow 2.9 | Scheduling, monitoring, retry |
| Orchestration (alt) | Prefect 2.x | Alternative orchestrator — Python-native |
| Database | PostgreSQL 15 | Persistent storage for pipeline data |
| Transformation | Pandas 2.x + NumPy | Data cleaning, validation, reshaping |
| HTTP Client | Requests | API calls with retry and backoff |
| DB Driver | psycopg2-binary | PostgreSQL connection from Python |
| Containers | Docker + Compose | Reproducible deployment |
| Message Queue | Redis | Airflow Celery task broker |
| Testing | pytest + pytest-mock | Unit tests and mocked API calls |
| Secrets | python-dotenv | Environment variable management |
| Version Control | Git + GitHub | Source control and collaboration |

---

## Project Structure

```
data_pipeline_project/
│
├── src/                              # All Python source code
│   ├── config.py                     # Central configuration — single source of truth
│   ├── logger.py                     # Structured logging (file + terminal)
│   ├── exceptions.py                 # Custom exception hierarchy
│   ├── utils.py                      # HTTP client with retry and backoff
│   ├── date_utils.py                 # UTC-aware datetime utilities
│   ├── database.py                   # PostgreSQL connection context manager
│   ├── loader.py                     # Bulk insert with ON CONFLICT DO NOTHING
│   ├── pipeline.py                   # Main ETL entrypoint
│   ├── pipeline_run.py               # Audit trail context manager
│   ├── alerting.py                   # Critical/warning alert routing
│   ├── health_checks.py              # Freshness and anomaly detection
│   ├── reports.py                    # Daily summary report generation
│   │
│   ├── extractors/
│   │   ├── weather_extractor.py      # OpenWeatherMap API client
│   │   ├── exchange_rate_extractor.py# Exchange rate API client
│   │   ├── github_extractor.py       # GitHub REST API client
│   │   └── nasa_extractor.py         # NASA APOD API client
│   │
│   └── transformers/
│       ├── weather_transformer.py    # Flatten, clean, validate, enrich
│       ├── exchange_rate_transformer.py # Wide-to-long reshape
│       ├── github_transformer.py     # Type conversion, derived metrics
│       ├── nasa_transformer.py       # Handles image/video schema differences
│       ├── combine.py                # Cross-source DataFrame merging
│       └── quality_checks.py        # Validation gate (FAILURE vs WARNING)
│
├── airflow/
│   └── dags/
│       └── pipeline_dag.py          # Airflow DAG with parallel extraction
│
├── prefect/
│   ├── pipeline_flow.py             # Prefect flow — same pipeline, less boilerplate
│   ├── deploy.py                    # Scheduled deployment configuration
│   └── block_setup.py               # Encrypted credential blocks
│
├── sql/
│   ├── schema.sql                   # OLTP schema — tables, indexes, views, functions
│   └── warehouse_schema.sql         # OLAP star schema for analytical queries
│
├── tests/
│   ├── test_transformers.py         # Unit tests for cleaning logic
│   ├── test_quality_checks.py       # Tests for validation gate
│   └── test_utils.py                # Mocked HTTP request tests
│
├── config/
│   ├── secrets.env                  # ← NOT committed (in .gitignore)
│   └── secrets.env.example          # Template — safe to commit
│
├── Dockerfile                       # Pipeline image (python:3.11-slim base)
├── Dockerfile.airflow               # Extended Airflow image with our dependencies
├── docker-compose.yml               # Pipeline + PostgreSQL stack
├── docker-compose.airflow.yml       # Full Airflow cluster (5 services)
├── docker-compose.prod.yml          # Production overrides
├── .dockerignore
├── .gitignore
└── requirements.txt
```

---

## Key Engineering Concepts

### Idempotency
The most important property of a data pipeline. Every load uses `INSERT ... ON CONFLICT (city_id, recorded_at) DO NOTHING`. The pipeline can crash and be restarted safely — duplicates are silently skipped, not inserted.

### The Landing Layer (ELT over ETL)
Raw API responses are saved to disk as JSON before any transformation. This enables:
- **Replay**: fix a transformation bug and reprocess without hitting the API again
- **Debugging**: the original data is always available for inspection
- **Compliance**: proof of exactly what a third-party API returned at a specific timestamp
- **Rate limit protection**: re-extract only what is missing, not everything

### Data Quality Gates
A validation layer runs after cleaning and before loading. It distinguishes:
- **FAILURES** — block the pipeline. NULL in a required column, temperature of 200°C, duplicate natural keys. These indicate data that is wrong, not merely suspicious.
- **WARNINGS** — log and continue. Slightly stale data, fewer cities than expected. These indicate conditions worth investigating but where loading is still better than discarding.

This distinction prevents alert fatigue — if every minor anomaly halts the pipeline, engineers stop reading the alerts.

### Exponential Backoff
Every HTTP call retries with increasing wait times: 2 seconds, then 4, then 8. This is the universal retry pattern across AWS, Airflow, Kubernetes, and all distributed systems. It prevents hammering a struggling server while still recovering from transient failures.

### Audit Trail
Every pipeline run creates a record in `pipeline_runs` before any work starts, and updates it to `success` or `failed` regardless of what happens. Six months from now, you can answer: "did the pipeline run last Tuesday? did it load all records? what error caused Monday's failure?"

---

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL 15
- Docker Desktop (for Airflow)
- Git

### 1. Clone and Set Up

```bash
git clone https://github.com/dinicharia/data-pipeline-project.git
cd data_pipeline_project

# Create and activate virtual environment
python -m venv venv
source venv/Scripts/activate    # Windows Git Bash
# source venv/bin/activate      # Mac / Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Secrets

```bash
# Copy the example file
cp config/secrets.env.example config/secrets.env

# Edit with your real values
# You need: OpenWeatherMap key, GitHub token, NASA key (or use DEMO_KEY)
```

Get your free API keys:
- **OpenWeatherMap**: [openweathermap.org](https://openweathermap.org) → Sign Up → API Keys
- **NASA**: [api.nasa.gov](https://api.nasa.gov) → Generate API Key (or use `DEMO_KEY`)
- **GitHub**: Settings → Developer Settings → Personal Access Tokens → Tokens (classic) → `repo` scope
- **Exchange Rates**: No key needed — uses the free [open.er-api.com](https://open.er-api.com) endpoint

```bash
# config/secrets.env
WEATHER_API_KEY=your_openweathermap_key
GITHUB_TOKEN=ghp_your_token
NASA_API_KEY=your_nasa_key_or_DEMO_KEY

DB_HOST=localhost
DB_PORT=5432
DB_NAME=pipeline_db
DB_USER=pipeline_user
DB_PASSWORD=your_password

LOG_LEVEL=INFO
ENVIRONMENT=development
```

### 3. Set Up PostgreSQL

```bash
# Connect as postgres admin user
psql -U postgres

# Create the pipeline user and database
CREATE USER pipeline_user WITH PASSWORD 'your_password';
CREATE DATABASE pipeline_db OWNER pipeline_user;
GRANT ALL PRIVILEGES ON DATABASE pipeline_db TO pipeline_user;
\q

# Run the schema
psql -U pipeline_user -d pipeline_db -f sql/schema.sql
```

---

## Running the Pipeline

```bash
# Dry run — extract and transform but skip loading to the database
# Safe to run at any time without side effects
python src/pipeline.py --dry-run

# Full run — extract, transform, validate, and load
python src/pipeline.py
```

**Expected output:**
```
╔══════════════════════════════════════════════════════╗
║           DATA PIPELINE STARTING                    ║
╚══════════════════════════════════════════════════════╝
...
STAGE 1: EXTRACT
  ✓ Weather extraction complete      (5 cities)
  ✓ Exchange rates extraction complete (7 currencies)
  ✓ GitHub extraction complete       (4 repositories)
  ✓ NASA extraction complete         (7 records)

STAGE 2: TRANSFORM
  ✓ Weather transform complete: 5 rows — quality gate passed
  ✓ Exchange rates transform complete: 7 rows
  ...

STAGE 3: LOAD
  ✓ Weather loaded: 5 rows inserted, 0 duplicates skipped
  ✓ Exchange rates loaded: 7 rows inserted
  ✓ Materialized view refreshed
╔══════════════════════════════════════════════════════╗
║           DATA PIPELINE COMPLETE                    ║
╚══════════════════════════════════════════════════════╝
```

**Verify the data landed:**
```sql
-- Connect to your database
psql -U pipeline_user -d pipeline_db

-- Weather data with the enriched view
SELECT city, country, temperature_c, temperature_f,
       humidity_pct, description, recorded_at
FROM v_weather_enriched
ORDER BY temperature_c DESC;

-- Pipeline audit trail
SELECT pipeline_name, status, started_at,
       records_loaded, error_message
FROM pipeline_runs
ORDER BY started_at DESC
LIMIT 10;
```

---

## Running with Apache Airflow

Airflow requires Docker on Windows (it uses Unix process forking natively).

```bash
# Copy your real credentials to the Docker env file
cp config/secrets.env .env
# Edit .env and set DB_HOST=host.docker.internal

# Initialise and start Airflow (first time takes 2-3 minutes)
docker compose -f docker-compose.airflow.yml up airflow-init
docker compose -f docker-compose.airflow.yml up -d

# Check all services are healthy
docker compose -f docker-compose.airflow.yml ps
```

Open **http://localhost:8080** (username: `admin`, password: `admin`)

- Find `data_pipeline_etl` in the DAG list
- Toggle it **ON** with the blue switch
- Click ▶ **Trigger DAG** to run immediately
- Click the DAG name → **Graph** view to watch tasks execute in real time

The DAG is scheduled to run automatically at **06:00 UTC every day**.

---

## Running with Prefect

Prefect runs natively on Windows — no Docker required.

```bash
# Terminal 1: start the Prefect server
prefect server start

# Terminal 2: run the pipeline
python prefect/pipeline_flow.py
```

Open **http://localhost:4200** to see:
- Every flow run with pass/fail status
- Individual task logs and durations
- A timeline showing which tasks ran in parallel

**Register the daily schedule:**
```bash
python prefect/deploy.py
prefect worker start --pool "default-agent-pool"
```

---

## Database Schema

The schema follows **Third Normal Form (3NF)** — each fact is stored exactly once.

```
cities (reference data)          weather_readings (fact table)
─────────────────────            ────────────────────────────────────
id           SERIAL PK           id             SERIAL PK
name         VARCHAR NOT NULL     city_id        INTEGER → cities(id)
country      VARCHAR NOT NULL     temperature_c  NUMERIC(5,2)  CHECK (-90..60)
latitude     NUMERIC CHECK        humidity_pct   INTEGER       CHECK (0..100)
longitude    NUMERIC CHECK        pressure_hpa   NUMERIC       CHECK (800..1100)
timezone     VARCHAR              wind_speed_ms  NUMERIC       CHECK (≥ 0)
UNIQUE(name, country)            description    VARCHAR
                                 recorded_at    TIMESTAMPTZ
                                 UNIQUE(city_id, recorded_at)  ← idempotency

exchange_rates                   pipeline_runs (audit log)
──────────────────               ────────────────────────────────────
base_currency   CHAR(3)          pipeline_name  VARCHAR
target_currency CHAR(3)          status         CHECK (running|success|failed)
rate            NUMERIC(18,8)    started_at     TIMESTAMPTZ
recorded_at     TIMESTAMPTZ      completed_at   TIMESTAMPTZ
UNIQUE(base, target, recorded_at)records_loaded INTEGER
                                 error_message  TEXT
```

**Indexes** on `city_id`, `recorded_at DESC`, and `(city_id, recorded_at DESC)` ensure queries remain fast even as millions of rows accumulate.

**Views** pre-join the most common query patterns so application code stays simple:
- `v_weather_enriched` — weather data with city metadata and Fahrenheit conversion
- `v_daily_city_summary` — per-city daily aggregates
- `mv_city_stats` — materialized view refreshed after every pipeline run

---

## Testing

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=src --cov-report=term-missing
```

The test suite covers:

**Unit tests** (`tests/test_transformers.py`) — test cleaning logic in isolation using invented data. No database, no API, no file system. Each test is fast and deterministic.

**Validation tests** (`tests/test_quality_checks.py`) — verify that failures block the pipeline and warnings do not. Confirm the distinction between genuinely bad data and merely suspicious data.

**Mocked HTTP tests** (`tests/test_utils.py`) — test retry logic, error handling, and backoff behaviour without making real network calls. `unittest.mock.patch` replaces `requests.get` with a controlled fake.

```python
# Example: testing that a 401 response raises APIAuthError immediately (no retry)
def test_401_raises_api_auth_error(self):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)

    with patch("src.utils.requests.get", return_value=mock_response):
        with pytest.raises(APIAuthError):
            safe_request("https://fake-api.com/weather")
```

---

## Design Decisions

**Why PostgreSQL?**
PostgreSQL handles everything from a startup's first database to Spotify's analytics infrastructure. It is the most capable open-source relational database, supports advanced SQL features (window functions, CTEs, full-text search), and is the dominant choice for Data Engineering roles.

**Why save raw data before transforming?**
If your transformation logic has a bug discovered three weeks later, you can fix it and reprocess from the raw files without re-hitting the API or losing the original data. This is the landing layer pattern — the first principle of modern ELT pipelines.

**Why `ON CONFLICT DO NOTHING` instead of `INSERT OR REPLACE`?**
Replace would silently overwrite existing valid data. `DO NOTHING` skips duplicates and reports how many were skipped, making the pipeline's behaviour auditable. Combined with the `UNIQUE (city_id, recorded_at)` constraint, it is impossible to accidentally create a duplicate record.

**Why separate FAILURE from WARNING in quality checks?**
A pipeline that is too strict eventually becomes one nobody trusts. If slightly stale data (e.g., 25-hour-old readings due to a scheduler delay) halts the entire pipeline, engineers start ignoring alerts. Reserving FAILURE for genuinely wrong data (impossible temperatures, NULL in required columns) keeps the signal meaningful.

**Why both Airflow and Prefect?**
They represent two different philosophies. Airflow requires you to write configuration describing a graph. Prefect lets you write Python that is a pipeline. Different companies use different tools — knowing both from hands-on experience makes you hireable at either.

---

## What I Learned

Building this project from scratch covered the full Data Engineering stack:

- Structuring a Python project professionally — virtual environments, centralised configuration, custom exception hierarchies, structured logging
- SQL from basic SELECT to advanced window functions, CTEs, indexes, views, stored procedures, and transactions
- REST API patterns — authentication, rate limiting, pagination, exponential backoff, and the ELT landing layer principle
- Data cleaning with Pandas — flattening nested JSON, type conversion, missing value policy, range validation, deduplication, and feature engineering
- Database design — normalisation, constraints, indexes, and the difference between OLTP schemas and OLAP star schemas
- Orchestration with Apache Airflow — DAGs, operators, parallel execution, XCom, retry logic, and running a full Celery/Redis cluster in Docker
- Orchestration with Prefect — flows, tasks, Blocks, and a direct hands-on comparison with Airflow
- Docker — Dockerfiles, layer caching, bind mounts, named volumes, multi-service Compose stacks, and container networking
- Testing — unit tests, mocking external dependencies, and the difference between testing logic and testing integration
- Production patterns — idempotency, audit trails, health checks, anomaly detection, alerting, secrets management, and deployment checklists

---

## Licence

MIT — free to use, modify, and distribute with attribution.

---
