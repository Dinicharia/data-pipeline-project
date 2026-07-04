# Data Pipeline Project

A production-quality ETL pipeline that collects data from public APIs,
transforms and validates it, loads it into PostgreSQL, and orchestrates
everything with Apache Airflow — fully containerized with Docker.

## Architecture

APIs (Weather, Exchange Rates, GitHub, NASA)
│
▼
Extract (Python)
│
▼
Raw JSON (Landing Layer)
│
▼
Transform + Validate (Pandas)
│
▼
PostgreSQL (pipeline_db)
│
▼
Airflow DAG (scheduled 06:00 UTC daily)

## Tech Stack

| Layer          | Technology                    |
|---------------|-------------------------------|
| Language       | Python 3.11                   |
| Orchestration  | Apache Airflow 2.9 / Prefect  |
| Database       | PostgreSQL 15                 |
| Transformation | Pandas 2.x                    |
| Containerization| Docker + Docker Compose      |
| Testing        | pytest + pytest-mock          |
| APIs           | OpenWeatherMap, NASA, GitHub  |

## Quick Start

### Prerequisites
- Docker Desktop
- Python 3.11+
- Git

### Local Setup

```bash
# Clone and enter the project
git clone https://github.com/yourusername/data-pipeline-project
cd data-pipeline-project

# Create virtual environment
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash

# Install dependencies
pip install -r requirements.txt

# Configure secrets
cp config/secrets.env.example config/secrets.env
# Edit config/secrets.env with your API keys
```

### Database Setup

```bash
# Initialize PostgreSQL schema
psql -U pipeline_user -d pipeline_db -f sql/schema.sql
```

### Run the Pipeline

```bash
# Single run (local)
python src/pipeline.py

# Dry run (no database writes)
python src/pipeline.py --dry-run

# With Airflow (Docker)
docker compose -f docker-compose.airflow.yml up -d
# Open http://localhost:8080 (admin/admin)

# With Prefect (local)
prefect server start
python prefect/pipeline_flow.py
```

### Run Tests

```bash
pytest tests/ -v --cov=src
```

## Project Structure

data_pipeline_project/
├── src/
│   ├── extractors/          # API clients (weather, rates, github, nasa)
│   ├── transformers/        # Pandas cleaning and validation
│   ├── config.py            # Central configuration
│   ├── database.py          # PostgreSQL connection management
│   ├── loader.py            # Bulk insert with conflict handling
│   ├── pipeline.py          # Main ETL entrypoint
│   └── ...
├── airflow/
│   └── dags/
│       └── pipeline_dag.py  # Airflow DAG definition
├── prefect/
│   └── pipeline_flow.py     # Prefect flow definition
├── sql/
│   ├── schema.sql           # OLTP schema (tables, indexes, views)
│   └── warehouse_schema.sql # OLAP star schema
├── tests/                   # pytest test suite
├── config/
│   └── secrets.env.example  # Template — never commit the real one
├── Dockerfile               # Pipeline container image
├── docker-compose.yml       # Full stack (pipeline + postgres)
├── docker-compose.airflow.yml # Airflow cluster
└── requirements.txt

## Data Sources

| Source          | Endpoint                    | Schedule     |
|-----------------|-----------------------------|--------------| 
| OpenWeatherMap  | /data/2.5/weather           | Every 6 hours|
| Exchange Rates  | open.er-api.com/v6/latest   | Daily        |
| GitHub API      | /repos/{owner}/{repo}       | Daily        |
| NASA APOD       | api.nasa.gov/planetary/apod | Daily        |

## Key Design Decisions

**ELT over ETL**: Raw API responses are saved to disk before
transformation, enabling replay without re-hitting APIs.

**Idempotent loads**: `ON CONFLICT DO NOTHING` means the pipeline
can restart safely without creating duplicates.

**Quality gates**: Data is validated against range constraints before
loading — bad data is rejected at the door, not discovered later.

**Audit trail**: Every pipeline run is recorded in `pipeline_runs`
with status, record counts, and error messages.