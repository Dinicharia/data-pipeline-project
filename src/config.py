# src/config.py
# This file is the single place where ALL configuration is loaded.
# Every other file in the project imports from here.
# This is called the "Single Source of Truth" pattern.

import os                          # built-in: access to operating system
from dotenv import load_dotenv     # loads .env file into environment
from pathlib import Path           # modern way to handle file paths

# ─── Locate and load the secrets file ────────────────────────────────────────
# Path(__file__) = the path to THIS file (src/config.py)
# .parent        = the folder containing it (src/)
# .parent        = one level up (project root)
PROJECT_ROOT = Path(__file__).parent.parent

# Load the .env file. After this line, os.getenv() can see all variables in it.
load_dotenv(PROJECT_ROOT / "config" / "secrets.env")


# ─── API Keys ─────────────────────────────────────────────────────────────────
# os.getenv("KEY") reads the variable from the environment
# The second argument is the default if the variable isn't found
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
# NASA provides a free demo key
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")


# ─── Database settings ────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))   # convert string → integer
DB_NAME = os.getenv("DB_NAME", "pipeline_db")
DB_USER = os.getenv("DB_USER", "pipeline_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


# ─── Project settings ─────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Build the full database URL (a standard format used by most DB libraries)
# Format: postgresql://user:password@host:port/database_name
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


# ─── Folder paths ─────────────────────────────────────────────────────────────
# Define all folder paths once here so nothing is hardcoded elsewhere
DATA_DIR = PROJECT_ROOT / "data"    # where raw API data is saved
LOG_DIR = PROJECT_ROOT / "logs"    # where log files are written

# Create folders if they don't exist yet
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


# ─── Quick self-check when run directly ───────────────────────────────────────
# This block only runs when you do: python src/config.py
# It does NOT run when another file imports this module
if __name__ == "__main__":
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Environment  : {ENVIRONMENT}")
    print(f"Log level    : {LOG_LEVEL}")
    print(f"DB host      : {DB_HOST}:{DB_PORT}/{DB_NAME}")
    # Never print secrets — just confirm they loaded
    print(f"Weather key loaded : {'YES' if WEATHER_API_KEY else 'NO'}")
    print(f"GitHub token loaded: {'YES' if GITHUB_TOKEN else 'NO'}")
    print(f"NASA key loaded    : {'YES' if NASA_API_KEY else 'NO'}")
