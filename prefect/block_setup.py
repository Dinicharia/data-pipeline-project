# prefect/block_setup.py
# Registers reusable credential blocks in Prefect.
# Run ONCE after starting the Prefect server:
#
#   prefect server start          (Terminal 1)
#   python prefect/block_setup.py (Terminal 2)
#
# Blocks are stored in Prefect's local database and visible
# at localhost:4200 → Blocks

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prefect.blocks.system import Secret
from src.config import WEATHER_API_KEY, GITHUB_TOKEN, NASA_API_KEY


def create_blocks():
    """
    Register API credentials as encrypted Prefect Blocks.

    WHY blocks instead of environment variables?
    Blocks are:
      - Stored encrypted in Prefect's database
      - Versioned — you can see when a credential changed
      - Reusable across multiple flows
      - Manageable via UI without touching code
      - Auditable — Prefect logs when a block is accessed
    """

    # ── Weather API key ───────────────────────────────────────────────────
    weather_block = Secret(value=WEATHER_API_KEY)
    weather_block.save("weather-api-key", overwrite=True)
    print("✅ Created block: weather-api-key")

    # ── GitHub token ──────────────────────────────────────────────────────
    github_block = Secret(value=GITHUB_TOKEN)
    github_block.save("github-token", overwrite=True)
    print("✅ Created block: github-token")

    # ── NASA API key ──────────────────────────────────────────────────────
    nasa_block = Secret(value=NASA_API_KEY)
    nasa_block.save("nasa-api-key", overwrite=True)
    print("✅ Created block: nasa-api-key")

    print("\nAll blocks registered.")
    print("View them at: http://localhost:4200/blocks")
    print("\nTo use a block in a flow:")
    print('  from prefect.blocks.system import Secret')
    print('  key = Secret.load("weather-api-key").get()')


if __name__ == "__main__":
    create_blocks()