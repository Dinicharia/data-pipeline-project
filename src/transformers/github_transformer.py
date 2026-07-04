# src/transformers/github_transformer.py
# GitHub's raw JSON is already mostly flat (we extracted clean fields
# in the extractor itself). This transformer focuses on type conversion
# and calculating useful derived metrics.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.config     import DATA_DIR
from src.utils      import load_json
from src.logger     import get_logger

logger = get_logger(__name__)


def transform_github_repos(filepath) -> pd.DataFrame:
    """
    Transform raw GitHub repo stats into a clean DataFrame.

    Args:
        filepath: Path to raw github JSON file

    Returns:
        Cleaned DataFrame with derived popularity metrics
    """
    raw = load_json(filepath)
    df  = pd.DataFrame(raw)

    # ── Convert GitHub's ISO timestamps to proper datetime ──────────────────
    # GitHub returns timestamps like "2026-06-28T10:15:00Z"
    for col in ["created_at", "updated_at", "pushed_at", "_extracted_at"]:
        df[col] = pd.to_datetime(df[col], utc=True)

    df = df.rename(columns={"_extracted_at": "extracted_at"})

    # ── Handle missing values ────────────────────────────────────────────
    # Some repos genuinely have no license file — "Unknown" is honest here,
    # unlike filling a numeric column with a fake number, a text placeholder
    # for a genuinely-absent categorical value is safe and clear
    df["license"]     = df["license"].fillna("Unknown")
    df["description"] = df["description"].fillna("")
    df["language"]    = df["language"].fillna("Unknown")

    # ── Feature engineering: popularity ratios ──────────────────────────────
    # Forks-to-stars ratio: how much do people build on this vs just admire it
    df["fork_to_star_ratio"] = (df["forks"] / df["stars"]).round(3)

    # Issues-to-stars ratio: rough proxy for project health/maintenance burden
    df["issues_to_star_ratio"] = (df["open_issues"] / df["stars"]).round(4)

    # Days since last push — staleness indicator
    now = pd.Timestamp.now(tz="UTC")
    df["days_since_pushed"] = (now - df["pushed_at"]).dt.days

    # Repo age in years
    df["repo_age_years"] = ((now - df["created_at"]).dt.days / 365.25).round(1)

    logger.info(f"Transformed {len(df)} GitHub repos with derived metrics")

    return df


if __name__ == "__main__":
    from src.date_utils import make_filename
    filepath = DATA_DIR / "github" / make_filename("github_raw")

    df = transform_github_repos(filepath)

    print("\n=== Transformed GitHub Repos ===")
    print(df[[
        "full_name", "stars", "forks", "fork_to_star_ratio",
        "days_since_pushed", "repo_age_years", "license"
    ]].to_string(index=False))