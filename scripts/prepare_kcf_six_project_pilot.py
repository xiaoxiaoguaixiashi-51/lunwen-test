"""Freeze six workflow-compatibility targets before observing API outcomes."""

import argparse
import hashlib
import json
from pathlib import Path


TARGETS = [
    ("commons-cli", "org.apache.commons.cli.Parser", "processArgs"),
    ("commons-csv", "org.apache.commons.csv.CSVPrinter", "printComment"),
    ("commons-codec", "org.apache.commons.codec.language.ColognePhonetic", "colognePhonetic"),
    ("commons-collections4", "org.apache.commons.collections4.functors.InvokerTransformer", "transform"),
    ("jdom2", "org.jdom2.internal.ReflectionConstructor", "construct"),
    ("windward", "org.flmelody.core.context.AbstractHttpWindwardContext", "html"),
]


def select_targets(rows):
    selected = []
    for project, owner, method in TARGETS:
        matches = [row for row in rows if (row["project_id"], row["fqcn"], row["method"]) == (project, owner, method)]
        if len(matches) != 1 or not matches[0].get("source_sha256") or not matches[0].get("method_owner"):
            raise ValueError(f"Expected exactly one frozen target for {project}:{owner}.{method}")
        selected.append(matches[0])
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-index", type=int, default=0, help="Separately freeze remaining targets after an interrupted pilot")
    args = parser.parse_args()
    selected = select_targets(json.loads(args.method_list.read_text(encoding="utf-8")))
    if not 0 <= args.start_index < len(selected):
        raise ValueError("Invalid start index")
    selected = selected[args.start_index:]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(selected, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"targets": len(selected), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
