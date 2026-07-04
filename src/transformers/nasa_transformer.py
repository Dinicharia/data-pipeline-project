# src/transformers/nasa_transformer.py
# NASA's APOD API has a quirk: video entries have a DIFFERENT shape
# than image entries (different fields present/absent). This transformer
# demonstrates handling structurally inconsistent API responses.

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.config     import DATA_DIR
from src.utils      import load_json
from src.logger     import get_logger

logger = get_logger(__name__)


def transform_nasa_apod(filepath) -> pd.DataFrame:
    """
    Transform raw NASA APOD JSON into a clean DataFrame.

    Quirk: when media_type == "video", the "hdurl" field (high-res image
    URL) is absent, and a "thumbnail_url" appears instead. We normalize
    both cases into one consistent column set.

    Args:
        filepath: Path to raw nasa JSON file

    Returns:
        Cleaned DataFrame with one consistent schema regardless of media type
    """
    raw = load_json(filepath)
    df  = pd.DataFrame(raw)

    # ── Type conversion ──────────────────────────────────────────────────
    df["date"]         = pd.to_datetime(df["date"])
    df["_extracted_at"] = pd.to_datetime(df["_extracted_at"], utc=True)
    df = df.rename(columns={"_extracted_at": "extracted_at"})

    # ── Normalize the image/video inconsistency ─────────────────────────
    # .get() equivalent for DataFrames: columns may not exist at all if
    # NO records in this batch were videos — guard against KeyError
    if "hdurl" not in df.columns:
        df["hdurl"] = None
    if "thumbnail_url" not in df.columns:
        df["thumbnail_url"] = None

    # Build one unified "display_url" column regardless of media type:
    # use hdurl for images, thumbnail_url for videos
    df["display_url"] = df["hdurl"].fillna(df["thumbnail_url"]).fillna(df["url"])

    # ── Missing values ───────────────────────────────────────────────────
    df["copyright"] = df["copyright"].fillna("Public Domain / NASA")

    # ── Feature engineering ─────────────────────────────────────────────
    df["title_word_count"]       = df["title"].str.split().str.len()
    df["explanation_word_count"] = df["explanation"].str.split().str.len()
    df["is_video"]               = df["media_type"] == "video"

    logger.info(
        f"Transformed {len(df)} NASA APOD records "
        f"({df['is_video'].sum()} videos, {(~df['is_video']).sum()} images)"
    )

    return df


if __name__ == "__main__":
    from src.date_utils import make_filename
    filepath = DATA_DIR / "nasa" / make_filename("nasa_apod_raw")

    df = transform_nasa_apod(filepath)

    print("\n=== Transformed NASA APOD ===")
    print(df[[
        "date", "title", "is_video", "title_word_count", "copyright"
    ]].to_string(index=False))