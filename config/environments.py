# config/environments.py
# Environment-specific configuration.
# The ENVIRONMENT variable in secrets.env switches between them.

import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

configs = {
    "development": {
        "log_level"         : "DEBUG",
        "api_timeout"       : 30,
        "max_retries"       : 1,      # fail fast in dev — don't wait
        "batch_size"        : 10,
        "alert_on_failure"  : False,  # don't page anyone in dev
    },
    "staging": {
        "log_level"         : "INFO",
        "api_timeout"       : 15,
        "max_retries"       : 2,
        "batch_size"        : 100,
        "alert_on_failure"  : False,
    },
    "production": {
        "log_level"         : "INFO",
        "api_timeout"       : 10,
        "max_retries"       : 3,
        "batch_size"        : 1000,
        "alert_on_failure"  : True,   # page on-call engineer
    },
}

# Current environment config — import this anywhere
ENV_CONFIG = configs.get(ENVIRONMENT, configs["development"])