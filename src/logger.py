# src/logger.py
# Central logging setup for the entire project.
# Import get_logger() in any file to get a ready-to-use logger.

import sys                            # access to stdout (the terminal)
from pathlib import Path

# Add project root to path BEFORE importing src.config
# Import our config so we know where to save logs and what level to use
# We use a relative import because logger.py is inside the src/ package
sys.path.insert(0, str(Path(__file__).parent.parent))

# Now Python knows where to find the 'src' folder!
from src.config import LOG_DIR, LOG_LEVEL
import logging                        # Python's built-in logging library
from datetime import datetime         # to put today's date in the log filename

def get_logger(name: str) -> logging.Logger:
    """
    Create and return a logger with the given name.

    Usage in any other file:
        from src.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Starting extract...")

    Args:
        name: Usually pass __name__ so the log shows which file it came from

    Returns:
        A configured Logger instance
    """

    # Create a logger object with this name
    # If a logger with this name already exists, Python returns the same one
    logger = logging.getLogger(name)

    # Only configure it once — avoid adding duplicate handlers
    if logger.handlers:
        return logger

    # Set the minimum level to capture (from our config file)
    # INFO means: capture INFO, WARNING, ERROR, CRITICAL (but not DEBUG)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # ── Format: what each log line looks like ──────────────────────────────
    # Example output:
    # 2026-06-27 14:32:01 | INFO     | src.extractor | Successfully fetched weather data
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"     # human-readable timestamp
    )

    # ── Handler 1: Write to the terminal ───────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── Handler 2: Write to a log file ─────────────────────────────────────
    # A new file is created each day (date in the filename)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"pipeline_{today}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# ── Quick test when run directly ───────────────────────────────────────────────
if __name__ == "__main__":
    logger = get_logger(__name__)

    logger.debug("This is a DEBUG message — only shows if LOG_LEVEL=DEBUG")
    logger.info("Pipeline started successfully")
    logger.warning("API rate limit approaching — 80% used")
    logger.error("Failed to connect to database")
    logger.critical(
        "Pipeline completely failed — manual intervention required")

    print("\nCheck your logs/ folder — a log file was created there too!")
