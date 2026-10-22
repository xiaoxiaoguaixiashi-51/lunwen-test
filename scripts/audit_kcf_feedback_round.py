"""Audit actual incremental outcomes and coverage acceptance without model calls."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.utils.experiment_metadata import sha256_file
from src.utils.repair_integrity import check_repair_integrity
from scripts.summarize_kcf_api_smoke import summarize_calls
from scripts.summarize_kcf_pilot import junit_counts


def audit_suite(run_root, status_path):
    status = json.loads(status_path.read_text(encoding="utf-8"))
    folder = status_path.parent
    first_code = folder / "attempt_0.java.txt"
    adopted = run_root / "combined_xml" / f"round{status['round']}" / status["id"] / "jacoco.xml"
    if not first_code.exists() or not (folder / "attempt_0.json").exists():
        if adopted.exists():
            raise ValueError("Suite without execution evidence was adopted")
        return {"id": status["id"], "project_id": status["project_id"], "round": status["round"],
                "first_attempt_status": None, "final_status": status["status"],
                "semantic_review_required": True, "adopted_automatically": False,
                "integrity": {"ok": False, "errors": ["No completed first-attempt execution snapshot"]},
                "junit": junit_counts(""), "final_source": None, "final_source_sha256": None,
                "xml_file": "", "xml_sha256": None, "last_recorded_attempt_status": None}
    first = json.loads((folder / "attempt_0.json").read_text(encoding="utf-8"))
    attempts = sorted(folder.glob("attempt_*.json"))
    # Integrity sidecars have a different suffix, not an execution result.
    attempts = [path for path in attempts if path.stem.split("_")[-1].isdigit()]
    attempts.sort(key=lambda path: int(path.stem.split("_")[-1]))
    last = json.loads(attempts[-1].read_text(encoding="utf-8"))
    last_number = int(attempts[-1].stem.split("_")[-1])
    code = folder / f"attempt_{last_number}.java.txt"
    xml = status.get("xml_file", "")
    if xml:
        expected = run_root / "incremental_jacoco" / f"round{status['round']}" / f"attempt{last_number}"
        if not Path(xml).resolve().is_relative_to(expected.resolve()):
            raise ValueError("Execution XML is not isolated to its own attempt")
    integrity = check_repair_integrity(first_code.read_text(encoding="utf-8"), code.read_text(encoding="utf-8"))
    if adopted.exists():
        if status["status"] != "ok" or status.get("semantic_review_required") or not integrity["ok"]:
            raise ValueError("Invalid or unreviewed suite was adopted")
        if sha256_file(adopted) != sha256_file(xml):
            raise ValueError("Adopted XML differs from passing execution")
    junit = Path(xml).parent.parent / "junit.log" if xml else None
    return {"id": status["id"], "project_id": status["project_id"], "round": status["round"],
            "first_attempt_status": first["result"]["status"], "final_status": status["status"],
            "semantic_review_required": status.get("semantic_review_required", False),
            "adopted_automatically": adopted.exists(), "integrity": integrity,
            "junit": junit_counts(junit.read_text(encoding="utf-8")) if junit and junit.exists() else junit_counts(""),
            "final_source": str(code), "final_source_sha256": sha256_file(code),
            "xml_file": xml, "xml_sha256": sha256_file(xml) if xml else None,
            "last_recorded_attempt_status": last["result"]["status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    rows = [audit_suite(root, path) for path in sorted(root.glob("generated_tests/round*/*/status.json"))]
    calls = [json.loads(line) for line in (root / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    result = {"kind": "bounded_feedback_pilot_audit_not_formal_rq1", "incremental_suites": rows,
              "incremental_suite_count": len(rows), "cost_observations": summarize_calls(calls)}
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
