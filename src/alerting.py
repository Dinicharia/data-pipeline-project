# src/alerting.py
# Sends alerts when the pipeline fails or detects data anomalies.
# In production this connects to Slack, PagerDuty, or email.
# For our project we implement the pattern and log alerts.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import smtplib
import json
from email.mime.text        import MIMEText
from email.mime.multipart   import MIMEMultipart
from datetime               import datetime
from src.logger             import get_logger
from src.config             import ENVIRONMENT

logger = get_logger(__name__)


class PipelineAlerter:
    """
    Sends alerts through multiple channels.
    Implements the "alert routing" pattern:
      - Critical failures → immediate alert
      - Warnings         → batched daily digest
      - Info             → logged only
    """

    def __init__(self):
        self.alerts_today = []

    def critical(self, message: str, context: dict = None) -> None:
        """
        Send an immediate alert for critical failures.
        In production: pages on-call engineer via PagerDuty.
        """
        alert = {
            "severity"   : "CRITICAL",
            "message"    : message,
            "context"    : context or {},
            "timestamp"  : datetime.utcnow().isoformat(),
            "environment": ENVIRONMENT,
        }

        logger.critical(f"ALERT: {message} | context={context}")
        self.alerts_today.append(alert)

        # In production, replace this with:
        # self._send_slack(alert)
        # self._page_oncall(alert)
        self._log_alert(alert)

    def warning(self, message: str, context: dict = None) -> None:
        """Log a warning — batched into daily digest."""
        alert = {
            "severity" : "WARNING",
            "message"  : message,
            "context"  : context or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.warning(f"ALERT: {message}")
        self.alerts_today.append(alert)

    def _log_alert(self, alert: dict) -> None:
        """Write alert to a dedicated alerts log file."""
        from src.config import LOG_DIR
        alert_file = LOG_DIR / "alerts.jsonl"   # JSON Lines format

        with open(alert_file, "a") as f:
            f.write(json.dumps(alert) + "\n")

    def send_daily_digest(self) -> None:
        """
        Send a summary of all today's alerts.
        Called at the end of each pipeline run.
        """
        if not self.alerts_today:
            logger.info("No alerts today — pipeline ran cleanly")
            return

        critical = [a for a in self.alerts_today if a["severity"] == "CRITICAL"]
        warnings = [a for a in self.alerts_today if a["severity"] == "WARNING"]

        logger.info(
            f"Daily alert digest: "
            f"{len(critical)} critical, {len(warnings)} warnings"
        )


# Global alerter instance — import and use anywhere in the pipeline
alerter = PipelineAlerter()