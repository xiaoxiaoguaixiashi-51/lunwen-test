"""Route-aligned entry point for new KCF-UTG feedback runs.

The historical runner remains available for reproducing old evidence. This
adapter changes only the default label and configuration; callers can still
override either explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_stage_b_ours_full_feedback as legacy_runner


DEFAULT_CONFIG = "config/config.kcf_utg.yaml"
DEFAULT_APPROACH_NAME = "KCF_UTG"


def adapted_args(args: list[str]) -> list[str]:
    """Add route defaults without overriding explicit caller arguments."""
    result = list(args)
    if "--config" not in result:
        result.extend(["--config", DEFAULT_CONFIG])
    if "--approach-name" not in result:
        result.extend(["--approach-name", DEFAULT_APPROACH_NAME])
    return result


def main() -> None:
    sys.argv = [sys.argv[0], *adapted_args(sys.argv[1:])]
    legacy_runner.main()


if __name__ == "__main__":
    main()
