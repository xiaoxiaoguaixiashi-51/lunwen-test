"""Analyze focal-method coverage from Cobertura XML reports.

The RQ1 comparison is method-centric: EvoSuite, RAG+LLM, and Ours must be
scored on the same fixed focal methods, not on whole target classes or on
coverage-command success counts. This script maps each focal method to source
line ranges and unions Cobertura line hits within those ranges.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SUMMARY_FIELDS = [
    "approach",
    "methods_total",
    "methods_with_coverage_data",
    "ambiguous_methods",
    "focal_lines_total",
    "focal_lines_covered",
    "focal_line_rate",
    "focal_branches_total",
    "focal_branches_covered",
    "focal_branch_rate",
]

DETAIL_BASE_FIELDS = [
    "id",
    "target",
    "class_name",
    "method",
    "dcci",
    "line_ranges",
    "method_match_count",
]


@dataclass(frozen=True)
class MethodRange:
    start: int
    end: int


@dataclass
class FocalMethod:
    id: str
    target: str
    method: str
    dcci: str
    class_name: str
    ranges: list[MethodRange]


@dataclass
class LineCoverage:
    hits: int = 0
    branch_total: int = 0
    branch_covered: int = 0


CoverageByClass = dict[str, dict[int, LineCoverage]]


def load_method_items(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise ValueError(f"Unsupported method-list JSON shape: {path}")


def resolve_target_path(target: str, source_root: Path | None, prefix_maps: list[tuple[str, str]]) -> Path:
    mapped = target
    for old, new in prefix_maps:
        if mapped.startswith(old):
            mapped = new + mapped[len(old) :]
            break
    path = Path(mapped)
    if path.exists():
        return path
    if source_root and "src/main/java/" in target.replace("\\", "/"):
        rel = target.replace("\\", "/").split("src/main/java/", 1)[1]
        candidate = source_root / rel
        if candidate.exists():
            return candidate
    return path


def class_name_from_source(source_path: Path, source_text: str) -> str:
    package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", source_text, re.MULTILINE)
    package = package_match.group(1) if package_match else ""
    name = source_path.stem
    return f"{package}.{name}" if package else name


def mask_java_source(text: str) -> str:
    chars = list(text)
    i = 0
    while i < len(chars):
        nxt = text[i : i + 2]
        if nxt == "//":
            j = i
            while j < len(chars) and chars[j] != "\n":
                chars[j] = " "
                j += 1
            i = j
        elif nxt == "/*":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i + 1 < len(chars) and text[i : i + 2] != "*/":
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < len(chars):
                chars[i] = chars[i + 1] = " "
                i += 2
        elif chars[i] in {'"', "'"}:
            quote = chars[i]
            i += 1
            escaped = False
            while i < len(chars):
                current = chars[i]
                if current != "\n":
                    chars[i] = " "
                if current == quote and not escaped:
                    i += 1
                    break
                escaped = current == "\\" and not escaped
                if current != "\\":
                    escaped = False
                i += 1
        else:
            i += 1
    return "".join(chars)


def find_method_ranges(source_text: str, method_name: str) -> list[MethodRange]:
    masked = mask_java_source(source_text)
    line_starts = [0]
    for index, char in enumerate(masked):
        if char == "\n":
            line_starts.append(index + 1)
    ranges: list[MethodRange] = []
    method_re = re.compile(rf"\b{re.escape(method_name)}\s*\(")
    declaration_re = re.compile(
        rf"(?:^|[\s}}])(?:@\w+(?:\([^)]*\))?\s*)*"
        rf"(?:(?:public|protected|private|static|final|synchronized|abstract|native|strictfp)\s+)*"
        rf"(?:<[^>{{}};]+>\s*)?[\w$.\[\]<>?,\s]+\s+{re.escape(method_name)}\s*\("
    )

    for match in method_re.finditer(masked):
        start = max(
            masked.rfind(";", 0, match.start()),
            masked.rfind("{", 0, match.start()),
            masked.rfind("}", 0, match.start()),
        ) + 1
        while start < len(masked) and masked[start].isspace():
            start += 1
        open_brace = masked.find("{", match.end())
        semicolon = masked.find(";", match.end())
        if open_brace < 0 or (semicolon >= 0 and semicolon < open_brace):
            continue
        declaration = " ".join(masked[start:open_brace].split())
        if not declaration_re.search(declaration):
            continue
        close_brace = find_matching_brace_offset(masked, open_brace)
        ranges.append(
            MethodRange(
                line_number_for_offset(line_starts, start),
                line_number_for_offset(line_starts, close_brace),
            )
        )
    return ranges


def find_owned_method_ranges(source_text: str, method_name: str, owner: str,
                             parameter_types: list[str] | None = None) -> list[MethodRange]:
    import javalang
    from src.utils.focal_target import select_method

    tree = javalang.parse.parse(source_text)
    _, method = select_method(tree, method_name, owner, parameter_types)
    if method.body is None or method.position is None:
        raise ValueError(f"Focal declaration has no executable body: {owner}.{method_name}")
    masked = mask_java_source(source_text)
    starts = [0] + [index + 1 for index, char in enumerate(masked) if char == "\n"]
    start = starts[method.position.line - 1] + method.position.column - 1
    opening = masked.find("{", start)
    if opening < 0:
        raise ValueError(f"Focal body not found: {owner}.{method_name}")
    closing = find_matching_brace_offset(masked, opening)
    return [MethodRange(method.position.line, line_number_for_offset(starts, closing))]


def line_number_for_offset(line_starts: list[int], offset: int) -> int:
    return bisect.bisect_right(line_starts, offset)


def find_matching_brace_offset(text: str, open_brace: int) -> int:
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(text) - 1


def load_focal_methods(method_list: Path, source_root: Path | None, prefix_maps: list[tuple[str, str]]) -> list[FocalMethod]:
    focal_methods: list[FocalMethod] = []
    for item in load_method_items(method_list):
        target = str(item.get("target", ""))
        method = str(item.get("method", ""))
        source_path = resolve_target_path(target, source_root, prefix_maps)
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        owner = item.get("method_owner")
        ranges = (
            find_owned_method_ranges(source_text, method, owner, item.get("method_parameter_types"))
            if owner else find_method_ranges(source_text, method)
        )
        focal_methods.append(
            FocalMethod(
                id=str(item.get("id", "")),
                target=target,
                method=method,
                dcci=str(item.get("dcci", item.get("score", ""))),
                class_name=class_name_from_source(source_path, source_text),
                ranges=ranges,
            )
        )
    return focal_methods


def parse_approach(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("approach must use NAME=XML_ROOT")
    name, root = value.split("=", 1)
    if not name.strip():
        raise argparse.ArgumentTypeError("approach name is empty")
    return name.strip(), Path(root)


def parse_prefix_map(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("prefix map must use OLD=NEW")
    old, new = value.split("=", 1)
    return old, new


def load_coverage_xmls(root: Path) -> CoverageByClass:
    coverage: CoverageByClass = {}
    for xml_path in sorted(root.rglob("*.xml")):
        merge_coverage_xml(xml_path, coverage)
    return coverage


def merge_coverage_xml(xml_path: Path, coverage: CoverageByClass):
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return
    root = tree.getroot()
    if root.tag == "report":
        merge_jacoco_root(root, coverage)
    else:
        merge_cobertura_root(root, coverage)


def merge_cobertura_xml(xml_path: Path, coverage: CoverageByClass):
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return
    merge_cobertura_root(tree.getroot(), coverage)


def merge_cobertura_root(root: ET.Element, coverage: CoverageByClass):
    for class_node in root.findall(".//class"):
        class_keys = class_keys_for_node(class_node)
        if not class_keys:
            continue
        for line_node in class_node.findall("./lines/line"):
            number_text = line_node.get("number", "")
            if not number_text.isdigit():
                continue
            line_no = int(number_text)
            line_cov = LineCoverage(
                hits=int_or_zero(line_node.get("hits", "")),
                branch_total=0,
                branch_covered=0,
            )
            covered, total = parse_condition_coverage(line_node.get("condition-coverage", ""))
            line_cov.branch_covered = covered
            line_cov.branch_total = total
            for key in class_keys:
                by_line = coverage.setdefault(key, {})
                existing = by_line.setdefault(line_no, LineCoverage())
                existing.hits = max(existing.hits, line_cov.hits)
                existing.branch_total = max(existing.branch_total, line_cov.branch_total)
                existing.branch_covered = max(existing.branch_covered, line_cov.branch_covered)


def merge_jacoco_root(root: ET.Element, coverage: CoverageByClass):
    for package_node in root.findall("./package"):
        package_name = package_node.get("name", "").replace("/", ".")
        for source_node in package_node.findall("./sourcefile"):
            source_name = source_node.get("name", "").strip()
            if not source_name:
                continue
            class_name = source_name[:-5] if source_name.endswith(".java") else source_name
            key = f"{package_name}.{class_name}" if package_name else class_name
            for line_node in source_node.findall("./line"):
                number_text = line_node.get("nr", "")
                if not number_text.isdigit():
                    continue
                line_no = int(number_text)
                covered_branches = int_or_zero(line_node.get("cb", ""))
                missed_branches = int_or_zero(line_node.get("mb", ""))
                line_cov = LineCoverage(
                    hits=int_or_zero(line_node.get("ci", "")),
                    branch_total=covered_branches + missed_branches,
                    branch_covered=covered_branches,
                )
                by_line = coverage.setdefault(key, {})
                existing = by_line.setdefault(line_no, LineCoverage())
                existing.hits = max(existing.hits, line_cov.hits)
                existing.branch_total = max(existing.branch_total, line_cov.branch_total)
                existing.branch_covered = max(existing.branch_covered, line_cov.branch_covered)


def class_keys_for_node(class_node: ET.Element) -> set[str]:
    keys: set[str] = set()
    name = class_node.get("name", "").strip()
    filename = class_node.get("filename", "").strip()
    if name:
        keys.add(name)
    if filename:
        normalized = filename.replace("\\", "/")
        keys.add(normalized)
        if normalized.endswith(".java"):
            keys.add(normalized[:-5].replace("/", "."))
    return keys


def int_or_zero(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_condition_coverage(value: str) -> tuple[int, int]:
    match = re.search(r"\((\d+)\s*/\s*(\d+)\)", value or "")
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def format_rate(covered: int, total: int) -> str:
    if total <= 0:
        return ""
    return f"{covered / total * 100:.1f}%"


def range_contains(ranges: list[MethodRange], line_no: int) -> bool:
    return any(method_range.start <= line_no <= method_range.end for method_range in ranges)


def score_method(method: FocalMethod, coverage: CoverageByClass,
                 reference: CoverageByClass | None = None) -> dict[str, str | int]:
    by_line = coverage.get(method.class_name, {})
    denominator = reference.get(method.class_name, {}) if reference is not None else by_line
    focal_line_numbers = sorted(line_no for line_no in denominator if range_contains(method.ranges, line_no))
    observed_lines = {n for n in by_line if range_contains(method.ranges, n)}
    if reference is not None:
        if not focal_line_numbers:
            raise ValueError(f"No canonical coverage denominator for {method.id}")
        if observed_lines - set(focal_line_numbers):
            raise ValueError(f"Observed lines outside canonical denominator for {method.id}")
        for number in observed_lines:
            if by_line[number].branch_total != denominator[number].branch_total:
                raise ValueError(f"Branch denominator mismatch for {method.id}:{number}")
    lines_total = len(focal_line_numbers)
    lines_covered = sum(1 for line_no in focal_line_numbers if by_line.get(line_no, LineCoverage()).hits > 0)
    branches_total = sum(denominator[line_no].branch_total for line_no in focal_line_numbers)
    branches_covered = sum(by_line.get(line_no, LineCoverage()).branch_covered for line_no in focal_line_numbers)
    return {
        "coverage_present": bool(observed_lines),
        "lines_total": lines_total,
        "lines_covered": lines_covered,
        "line_rate": format_rate(lines_covered, lines_total),
        "branches_total": branches_total,
        "branches_covered": branches_covered,
        "branch_rate": format_rate(branches_covered, branches_total),
    }


def write_outputs(focal_methods: list[FocalMethod], approaches: list[tuple[str, CoverageByClass]], output_dir: Path,
                  reference: CoverageByClass | None = None):
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_fields = DETAIL_BASE_FIELDS[:]
    for name, _coverage in approaches:
        detail_fields.extend(
            [
                f"{name}_lines_total",
                f"{name}_lines_covered",
                f"{name}_line_rate",
                f"{name}_branches_total",
                f"{name}_branches_covered",
                f"{name}_branch_rate",
            ]
        )

    details: list[dict] = []
    summaries: list[dict] = []
    for method in focal_methods:
        row = {
            "id": method.id,
            "target": method.target,
            "class_name": method.class_name,
            "method": method.method,
            "dcci": method.dcci,
            "line_ranges": ";".join(f"{r.start}-{r.end}" for r in method.ranges),
            "method_match_count": len(method.ranges),
        }
        for name, coverage in approaches:
            score = score_method(method, coverage, reference)
            row[f"{name}_lines_total"] = score["lines_total"]
            row[f"{name}_lines_covered"] = score["lines_covered"]
            row[f"{name}_line_rate"] = score["line_rate"]
            row[f"{name}_branches_total"] = score["branches_total"]
            row[f"{name}_branches_covered"] = score["branches_covered"]
            row[f"{name}_branch_rate"] = score["branch_rate"]
        details.append(row)

    for name, coverage in approaches:
        method_scores = [score_method(method, coverage, reference) for method in focal_methods]
        lines_total = sum(int(score["lines_total"]) for score in method_scores)
        lines_covered = sum(int(score["lines_covered"]) for score in method_scores)
        branches_total = sum(int(score["branches_total"]) for score in method_scores)
        branches_covered = sum(int(score["branches_covered"]) for score in method_scores)
        summaries.append(
            {
                "approach": name,
                "methods_total": len(focal_methods),
                "methods_with_coverage_data": sum(bool(score["coverage_present"]) for score in method_scores),
                "ambiguous_methods": sum(1 for method in focal_methods if len(method.ranges) != 1),
                "focal_lines_total": lines_total,
                "focal_lines_covered": lines_covered,
                "focal_line_rate": format_rate(lines_covered, lines_total),
                "focal_branches_total": branches_total,
                "focal_branches_covered": branches_covered,
                "focal_branch_rate": format_rate(branches_covered, branches_total),
            }
        )

    write_csv(output_dir / "focal_method_coverage_detail.csv", detail_fields, details)
    write_csv(output_dir / "focal_method_coverage_summary.csv", SUMMARY_FIELDS, summaries)
    write_json(output_dir / "focal_method_coverage_summary.json", summaries)


def write_csv(path: Path, fields: list[str], rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, rows: list[dict]):
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compute focal-method coverage from Cobertura XML files")
    parser.add_argument("--method-list", required=True, help="Fixed focal-method JSON list")
    parser.add_argument("--reference-xml-root", help="Canonical zero-coverage XML from the same compiled project versions")
    parser.add_argument("--source-root", default="", help="Source root used when method targets are from another host")
    parser.add_argument("--prefix-map", action="append", default=[], type=parse_prefix_map, help="Map OLD=NEW target prefixes")
    parser.add_argument("--approach", action="append", required=True, type=parse_approach, help="Approach XML root, NAME=PATH")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    args = parser.parse_args()

    source_root = Path(args.source_root) if args.source_root else None
    focal_methods = load_focal_methods(Path(args.method_list), source_root, args.prefix_map)
    approaches = [(name, load_coverage_xmls(root)) for name, root in args.approach]
    reference = load_coverage_xmls(Path(args.reference_xml_root)) if args.reference_xml_root else None
    write_outputs(focal_methods, approaches, Path(args.output_dir), reference)

    for name, coverage in approaches:
        xml_line_count = sum(len(lines) for lines in coverage.values())
        print(f"{name}: loaded {len(coverage)} class keys, {xml_line_count} covered/instrumented line entries")
    print(f"Wrote focal-method coverage outputs under {args.output_dir}")


if __name__ == "__main__":
    main()
