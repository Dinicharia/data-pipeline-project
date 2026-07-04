# prefect/deploy.py
# Creates a Prefect deployment — a flow configured to run on a schedule.
# This is the equivalent of Airflow's schedule="0 6 * * *" in the DAG.
#
# Run once to register the deployment:
#   python prefect/deploy.py
#
# Then start the worker to execute scheduled runs:
#   prefect worker start --pool "local-pool"

from prefect.client.schemas.schedules import CronSchedule
from prefect_deployments import deploy  # Prefect 2.x deployment API

# Import our flow
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prefect.deployments import Deployment
from prefect.infrastructure import Process
from prefect_pipeline_flow import run_pipeline


def create_deployment():
    """
    Register our pipeline as a scheduled deployment in Prefect.
    """
    deployment = Deployment.build_from_flow(
        flow=run_pipeline,
        name="daily-etl",
        schedule=CronSchedule(
            cron="0 6 * * *",      # same schedule as our Airflow DAG
            timezone="UTC"
        ),
        tags=["etl", "weather", "production"],
        description="Daily pipeline: extract APIs → transform → load PostgreSQL",
        work_queue_name="default",
    )

    deployment_id = deployment.apply()
    print(f"Deployment created: {deployment_id}")
    print("Start a worker to execute it:")
    print("  prefect worker start --pool 'default-agent-pool'")


if __name__ == "__main__":
    create_deployment()