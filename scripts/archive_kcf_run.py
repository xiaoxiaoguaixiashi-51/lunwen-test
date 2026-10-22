"""Archive one scoped cloud run only after scanning for its configured API key."""

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.summarize_kcf_api_smoke import summarize_calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--private-config", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    run_base = Path(__file__).resolve().parents[1] / "experiments/runs"
    if not root.is_dir() or not root.is_relative_to(run_base.resolve()) or root == run_base.resolve():
        raise ValueError("Export only an explicitly scoped experiment run")
    if args.archive.exists() or args.archive.resolve().is_relative_to(root):
        raise ValueError("Use a new archive outside the run directory")
    if args.log:
        if (root / "run.log").exists():
            raise FileExistsError("Existing log is retained")
        shutil.copy2(args.log, root / "run.log")
    calls = root / "llm_calls.jsonl"
    events = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines() if line.strip()] if calls.exists() else []
    summary = summarize_calls(events)
    summary_path = root / "cost_summary.json"
    if summary_path.exists():
        raise FileExistsError("Existing cost summary is retained")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    secret = yaml.safe_load(args.private_config.read_text(encoding="utf-8"))["llm"]["api_key"].encode()
    if not secret:
        raise ValueError("Missing key for evidence scan")
    for path in root.rglob("*"):
        if path.is_symlink() or (path.is_file() and secret in path.read_bytes()):
            raise ValueError("Export blocked by private-key/symlink scan")
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "w:gz") as archive:
        archive.add(root, arcname=root.name)
    print(json.dumps({"archive": str(args.archive), "sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                      "cost_observations": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
