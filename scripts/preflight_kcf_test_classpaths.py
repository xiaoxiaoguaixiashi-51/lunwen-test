"""Compile minimal target/JUnit references for every pilot method, without API."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core.batch_runner import load_method_list
from src.utils.compiler import JavaCompiler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method-list", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Keep previous preflight evidence")
    compiler = JavaCompiler(java_home="/usr/lib/jvm/java-8-openjdk-amd64")
    rows = []
    for method in load_method_list(args.method_list):
        owner = method["method_owner"].replace("$", ".")
        code = "public class ClasspathSmokeTest { @org.junit.Test public void check() { org.junit.Assert.assertNotNull(" + owner + ".class); } }"
        result = compiler.compile_test(code, source_file=method["target"])
        rows.append({"id": method["id"], "project_id": method["project_id"],
                     "success": result.success, "return_code": result.return_code, "errors": result.errors,
                     "classpath": compiler._classpath_for_source_file(method["target"])})
        print(method["project_id"], result.success, flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0 if all(row["success"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
