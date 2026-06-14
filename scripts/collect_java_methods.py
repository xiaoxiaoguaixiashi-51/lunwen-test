"""Collect Java focal-method candidates from a source tree."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

try:
    import javalang
except ImportError:
    javalang = None


def collect_methods(source_root: Path, project_id: str, source_label: str) -> list[dict]:
    rows: list[dict] = []
    for java_file in sorted(source_root.rglob("*.java")):
        rows.extend(collect_methods_from_file(java_file, source_root, project_id, source_label))
    return rows


def collect_methods_from_file(java_file: Path, source_root: Path, project_id: str, source_label: str) -> list[dict]:
    text = java_file.read_text(encoding="utf-8", errors="ignore")
    if javalang is None:
        return collect_methods_fallback(java_file, source_root, project_id, source_label, text)

    try:
        tree = javalang.parse.parse(text)
    except (javalang.parser.JavaSyntaxError, IndexError, TypeError):
        return collect_methods_fallback(java_file, source_root, project_id, source_label, text)

    package = tree.package.name if tree.package else ""
    method_decls = []
    for _, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        class_name = class_decl.name
        for method in class_decl.methods:
            if is_candidate_method(method):
                method_decls.append((package, class_name, method.name))

    return build_rows(java_file, source_root, project_id, source_label, method_decls)


def collect_methods_fallback(
    java_file: Path,
    source_root: Path,
    project_id: str,
    source_label: str,
    text: str,
) -> list[dict]:
    package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, flags=re.MULTILINE)
    class_match = re.search(r"\bclass\s+(\w+)\b", text)
    if not class_match:
        return []
    package = package_match.group(1) if package_match else ""
    class_name = class_match.group(1)
    method_names = [
        match.group("name")
        for match in re.finditer(
            r"\bpublic\s+(?:static\s+)?(?:[\w.<>, ?\[\]]+)\s+(?P<name>\w+)\s*\(",
            text,
        )
        if match.group("name") != class_name
    ]
    return build_rows(
        java_file,
        source_root,
        project_id,
        source_label,
        [(package, class_name, method_name) for method_name in method_names],
    )


def is_candidate_method(method) -> bool:
    modifiers = method.modifiers or set()
    return "public" in modifiers and "abstract" not in modifiers and method.body is not None


def build_rows(
    java_file: Path,
    source_root: Path,
    project_id: str,
    source_label: str,
    method_decls: list[tuple[str, str, str]],
) -> list[dict]:
    name_counts = Counter(method_name for _, _, method_name in method_decls)
    rows = []
    for package, class_name, method_name in method_decls:
        if name_counts[method_name] > 1:
            continue
        rel = java_file.relative_to(source_root).with_suffix("")
        fqcn = ".".join(part for part in [package, class_name] if part)
        rows.append(
            {
                "id": safe_id(project_id, str(rel), method_name),
                "target": str(java_file),
                "method": method_name,
                "source": source_label,
                "class_name": class_name,
                "package": package,
                "fqcn": fqcn,
            }
        )
    return rows


def safe_id(project_id: str, relative_class_path: str, method_name: str) -> str:
    raw = f"{project_id}-{relative_class_path}-{method_name}"
    return re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").lower()


def main():
    parser = argparse.ArgumentParser(description="Collect Java focal-method candidates from a source tree")
    parser.add_argument("--source-root", required=True, help="Java source root, e.g. src/main/java")
    parser.add_argument("--project-id", required=True, help="Stable project id prefix for generated method ids")
    parser.add_argument("--source-label", default="defects4j", help="Source label written into each row")
    parser.add_argument("--output", required=True, help="Output JSON method list")
    args = parser.parse_args()

    rows = collect_methods(Path(args.source_root), args.project_id, args.source_label)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} methods to {output}")


if __name__ == "__main__":
    main()
