"""Batch runner for cloud experiments.

The runner accepts a JSON method list and stores each method's output in an
independent directory so long experiments can be resumed safely.
"""

import argparse
import json
import hashlib
import os
from pathlib import Path

from src.core.llm_client import load_config, trace_target
from src.core.pipeline import Pipeline
from src.utils.experiment_metadata import write_run_metadata


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
        if item.get("source_sha256"):
            actual = hashlib.sha256(Path(item["target"]).read_bytes()).hexdigest()
            if actual != item["source_sha256"]:
                raise ValueError(f"Frozen source hash mismatch for {item['id']}")
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
            selector = {}
            if item.get("method_owner"):
                selector = {"method_owner": item["method_owner"],
                            "method_parameter_types": item.get("method_parameter_types")}
            with trace_target(method_id):
                result = pipeline.run(item["target"], item["method"], output_dir=str(item_dir), **selector)
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
    os.environ.setdefault("KCF_LLM_TRACE_PATH", str(Path(args.output).resolve() / "llm_calls.jsonl"))
    os.environ.setdefault("KCF_PHASE_TRACE_PATH", str(Path(args.output).resolve() / "phase_calls.jsonl"))
    os.environ.setdefault("KCF_EXPERIMENT_STAGE", "initial_generation")

    methods = load_method_list(args.methods)
    config = load_config(args.config)
    config_path = args.config or str(Path(__file__).resolve().parents[2] / "config" / "config.yaml")
    output_dir = Path(args.output)
    retrieval = config.get("retrieval", {})
    static_guard = config.get("static_guard", {})
    write_run_metadata(
        output_dir,
        stage="initial_generation",
        method_list=args.methods,
        config_path=config_path,
        config=config,
        knowledge_path=retrieval.get("knowledge_path"),
        settings={
            "method_count": len(methods),
            "resume": not args.no_resume,
            "knowledge_retrieval_enabled": bool(retrieval.get("enabled", False)),
            "static_guard_enabled": bool(static_guard.get("enabled", True)),
            "feedback_enabled": bool(config.get("pipeline", {}).get("feedback_enabled", True)),
            "max_fix_iterations": config.get("pipeline", {}).get("max_fix_iterations", 3),
        },
    )
    summary = run_batch(methods, args.output, config, resume=not args.no_resume)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
