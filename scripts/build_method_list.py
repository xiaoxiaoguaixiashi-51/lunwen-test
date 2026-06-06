"""Filter scored method lists for pilot/full experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_items(path: str) -> list[dict]:
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Input must be a JSON array")
    return items


def filter_items(items: list[dict], min_dcci: float, limit: int | None) -> list[dict]:
    selected = [item for item in items if float(item.get("dcci", 0.0)) >= min_dcci]
    selected.sort(key=lambda item: float(item.get("dcci", 0.0)), reverse=True)
    if limit is not None:
        selected = selected[:limit]
    return selected


def strip_for_runner(items: list[dict]) -> list[dict]:
    return [
        {
            "id": item["id"],
            "target": item["target"],
            "method": item["method"],
            "dcci": item.get("dcci"),
            "source": item.get("source", "unknown"),
        }
        for item in items
    ]


def main():
    parser = argparse.ArgumentParser(description="Build filtered method list from DCCI-scored candidates")
    parser.add_argument("--input", required=True, help="DCCI-scored input JSON")
    parser.add_argument("--output", required=True, help="Filtered output JSON")
    parser.add_argument("--min-dcci", type=float, default=1.0, help="Minimum DCCI threshold")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of methods")
    parser.add_argument(
        "--runner-only",
        action="store_true",
        help="Keep only fields needed by batch_runner plus DCCI/source metadata",
    )
    args = parser.parse_args()

    selected = filter_items(load_items(args.input), args.min_dcci, args.limit)
    if args.runner_only:
        selected = strip_for_runner(selected)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(selected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(selected)} methods to {out}")


if __name__ == "__main__":
    main()
