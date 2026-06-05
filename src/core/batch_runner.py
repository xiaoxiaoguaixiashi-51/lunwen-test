"""Batch runner for cloud experiments.

The runner accepts a JSON method list and stores each method's output in an
independent directory so long experiments can be resumed safely.
"""

import argparse
import json
from pathlib import Path

from src.core.llm_client import load_config
from src.core.pipeline import Pipeline


def load_method_list(method_list_path: str) -> list[dict]:
    """Load experiment targets from a JSON file."""
    path = Path(method_list_path)
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Method list must be a JSON array")

    required = {"id", "target", "method"}
    for index, item in enumerate(items):
        missing = required - set(item)
        if missing:
            raise ValueError(f"Method list item #{index} is missing fields: {sorted(missing)}")
    return items


def run_batch(methods: list[dict], output_dir: str, config: dict, resume: bool = True) -> dict:
    """Run the pipeline for a list of methods and write per-method results."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    pipeline = Pipeline(config)
    summary = {
        "total": len(methods),
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "items": [],
    }

    for item in methods:
        method_id = item["id"]
        item_dir = root / method_id
        status_file = item_dir / "status.json"

        if resume and status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            if status.get("status") == "completed":
                summary["skipped"] += 1
                summary["items"].append({"id": method_id, "status": "skipped"})
                continue

        item_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = pipeline.run(item["target"], item["method"], output_dir=str(item_dir))
            status = {
                "id": method_id,
                "target": item["target"],
                "method": item["method"],
                "status": "completed" if result.success else "failed",
                "success": result.success,
                "iterations": result.iterations,
            }
            if result.success:
                summary["completed"] += 1
            else:
                summary["failed"] += 1
        except Exception as exc:
            status = {
                "id": method_id,
                "target": item["target"],
                "method": item["method"],
                "status": "error",
                "error": str(exc),
            }
            summary["failed"] += 1

        status_file.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["items"].append(status)

    (root / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run batch Java test-generation experiments")
    parser.add_argument("--methods", required=True, help="JSON method list")
    parser.add_argument("--output", default="experiments/runs", help="Batch output directory")
    parser.add_argument("--config", default=None, help="Config file path")
    parser.add_argument("--no-resume", action="store_true", help="Rerun completed items")
    args = parser.parse_args()

    methods = load_method_list(args.methods)
    config = load_config(args.config)
    summary = run_batch(methods, args.output, config, resume=not args.no_resume)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
