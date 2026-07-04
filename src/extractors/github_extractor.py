# src/extractors/github_extractor.py
# Extracts public repository statistics from the GitHub API.
# Demonstrates: authentication headers, pagination, rate limit handling.
# Docs: https://docs.github.com/en/rest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config     import GITHUB_TOKEN, DATA_DIR
from src.utils      import safe_request, save_json
from src.date_utils import now_utc, make_filename
from src.logger     import get_logger
from src.exceptions import ExtractError

logger = get_logger(__name__)

BASE_URL = "https://api.github.com"

# Interesting public repos to track — good portfolio data
TRACKED_REPOS = [
    ("python",    "cpython"),       # Python language itself
    ("pandas-dev", "pandas"),       # pandas library
    ("apache",    "airflow"),       # Airflow (we'll use this in Phase 8)
    ("psf",       "requests"),      # the requests library we're using
]


def get_auth_headers() -> dict:
    """
    Build authentication headers for GitHub API.
    Without a token: 60 requests/hour
    With a token:  5,000 requests/hour
    """
    headers = {
        "Accept"               : "application/vnd.github.v3+json",
        "X-GitHub-Api-Version" : "2022-11-28",
    }

    if GITHUB_TOKEN:
        # Bearer token authentication — the standard for modern APIs
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        logger.debug("Using authenticated GitHub requests (5,000/hour limit)")
    else:
        logger.warning(
            "No GITHUB_TOKEN set — using unauthenticated requests (60/hour limit). "
            "Set GITHUB_TOKEN in config/secrets.env for higher limits."
        )

    return headers


def extract_repo_stats(owner: str, repo: str) -> dict:
    """
    Fetch statistics for one GitHub repository.

    Args:
        owner: GitHub username or org, e.g. "apache"
        repo:  Repository name, e.g. "airflow"

    Returns:
        Dict with repo metadata and statistics
    """
    headers = get_auth_headers()
    logger.info(f"Fetching GitHub stats: {owner}/{repo}")

    # Main repo info
    repo_data = safe_request(
        f"{BASE_URL}/repos/{owner}/{repo}",
        headers=headers,
    )

    # Extract only the fields we care about
    # The full response has 100+ fields — we take what's useful
    result = {
        "owner"            : owner,
        "repo"             : repo,
        "full_name"        : repo_data["full_name"],
        "description"      : repo_data.get("description"),
        "stars"            : repo_data["stargazers_count"],
        "forks"            : repo_data["forks_count"],
        "open_issues"      : repo_data["open_issues_count"],
        "watchers"         : repo_data["watchers_count"],
        "size_kb"          : repo_data["size"],
        "language"         : repo_data.get("language"),
        "created_at"       : repo_data["created_at"],
        "updated_at"       : repo_data["updated_at"],
        "pushed_at"        : repo_data["pushed_at"],
        "default_branch"   : repo_data["default_branch"],
        "license"          : repo_data.get("license", {}).get("name"),
        "_extracted_at"    : now_utc().isoformat(),
    }

    logger.debug(
        f"  {owner}/{repo}: "
        f"⭐ {result['stars']:,} stars, "
        f"🍴 {result['forks']:,} forks, "
        f"🐛 {result['open_issues']:,} open issues"
    )

    return result


def extract_all_repos() -> list[dict]:
    """
    Fetch stats for all tracked repositories and save to disk.

    Returns:
        List of repo stat dicts
    """
    logger.info(f"Starting GitHub extraction for {len(TRACKED_REPOS)} repositories")

    results = []
    failed  = []

    for owner, repo in TRACKED_REPOS:
        try:
            data = extract_repo_stats(owner, repo)
            results.append(data)

        except ExtractError as e:
            logger.error(f"Failed to extract {owner}/{repo}: {e}")
            failed.append(f"{owner}/{repo}")
            continue

    if results:
        filepath = DATA_DIR / "github" / make_filename("github_raw")
        DATA_DIR.joinpath("github").mkdir(exist_ok=True)
        save_json(results, filepath)
        logger.info(
            f"GitHub extraction complete: "
            f"{len(results)} succeeded, {len(failed)} failed"
        )

    if failed:
        logger.warning(f"Repos with extraction failures: {failed}")

    return results


if __name__ == "__main__":
    data = extract_all_repos()
    print(f"\nExtracted {len(data)} repositories\n")
    print(f"{'Repository':<30} {'Stars':>8} {'Forks':>8} {'Issues':>8}")
    print("-" * 60)
    for repo in data:
        print(
            f"{repo['full_name']:<30} "
            f"{repo['stars']:>8,} "
            f"{repo['forks']:>8,} "
            f"{repo['open_issues']:>8,}"
        )