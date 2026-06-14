"""DCCI scoring for Java focal methods.

DCCI (Dependency Construction Complexity Index) estimates how difficult a
method is to construct, isolate, mock, and assert in unit tests.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.utils.java_parser import DependencyInfo, extract_dependencies


@dataclass
class DcciBreakdown:
    external_calls: float
    dependency_classes: float
    injection_difficulty: float
    state_dependency: float
    resource_dependency: float
    oracle_difficulty: float
    parameter_complexity: float

    def weighted_score(self) -> float:
        return (
            0.25 * self.external_calls
            + 0.20 * self.dependency_classes
            + 0.15 * self.injection_difficulty
            + 0.15 * self.state_dependency
            + 0.10 * self.resource_dependency
            + 0.10 * self.oracle_difficulty
            + 0.05 * self.parameter_complexity
        )


def score_dependency_info(info: DependencyInfo) -> tuple[float, DcciBreakdown]:
    """Compute DCCI and component scores from extracted dependency info.

    Component scores are intentionally normalized to small interpretable values
    so a threshold like DCCI > 1 identifies methods with meaningful dependency
    construction difficulty in pilot experiments.
    """

    dependency_types = {
        item.get("type", "")
        for item in [*info.field_dependencies, *info.constructor_params]
        if item.get("type")
    }
    static_fields = [item for item in info.field_dependencies if item.get("is_static")]
    unique_call_targets = {
        item.get("target", "")
        for item in info.external_calls
        if item.get("target") and item.get("target") != "this"
    }

    external_calls = min(len(info.external_calls) / 3.0, 3.0)
    dependency_classes = min(len(dependency_types) / 2.0, 3.0)
    injection_difficulty = min((len(info.constructor_params) + len(info.field_dependencies)) / 3.0, 3.0)
    state_dependency = min(
        len(static_fields)
        + (1.0 if info.has_time_dependency else 0.0)
        + (0.5 if unique_call_targets else 0.0),
        3.0,
    )
    resource_dependency = min(
        (1.0 if info.has_io_dependency else 0.0)
        + (1.0 if info.has_random_dependency else 0.0)
        + (0.5 if info.has_time_dependency else 0.0),
        3.0,
    )
    oracle_difficulty = min(
        len(info.exceptions_thrown)
        + len(unique_call_targets) / 2.0
        + (1.0 if info.return_type and info.return_type != "void" else 0.0),
        3.0,
    )
    parameter_complexity = min(len(info.parameters) / 2.0, 3.0)

    breakdown = DcciBreakdown(
        external_calls=external_calls,
        dependency_classes=dependency_classes,
        injection_difficulty=injection_difficulty,
        state_dependency=state_dependency,
        resource_dependency=resource_dependency,
        oracle_difficulty=oracle_difficulty,
        parameter_complexity=parameter_complexity,
    )
    return round(breakdown.weighted_score(), 4), breakdown


def score_method(target: str, method: str | None = None) -> dict:
    info = extract_dependencies(target, method)
    score, breakdown = score_dependency_info(info)
    return {
        "target": target,
        "method": info.method_name,
        "class_name": info.class_name,
        "dcci": score,
        "dcci_breakdown": asdict(breakdown),
        "dependency_summary": {
            "external_calls": len(info.external_calls),
            "field_dependencies": len(info.field_dependencies),
            "constructor_params": len(info.constructor_params),
            "parameters": len(info.parameters),
            "has_time_dependency": info.has_time_dependency,
            "has_random_dependency": info.has_random_dependency,
            "has_io_dependency": info.has_io_dependency,
        },
    }


def score_method_list(items: list[dict], skip_errors: bool = False) -> list[dict]:
    scored = []
    for item in items:
        try:
            result = score_method(item["target"], item.get("method"))
        except Exception as exc:
            if not skip_errors:
                raise
            scored.append({**item, "dcci_error": f"{type(exc).__name__}: {exc}"})
            continue
        scored.append({**item, **result})
    return scored


def main():
    parser = argparse.ArgumentParser(description="Compute DCCI for Java focal methods")
    parser.add_argument("--target", help="Target Java file")
    parser.add_argument("--method", help="Target method name")
    parser.add_argument("--input", help="Input method-list JSON")
    parser.add_argument("--output", help="Output scored JSON")
    parser.add_argument("--skip-errors", action="store_true", help="Keep scoring remaining methods after parse errors")
    args = parser.parse_args()

    if args.input:
        items = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = score_method_list(items, skip_errors=args.skip_errors)
    elif args.target:
        result = score_method(args.target, args.method)
    else:
        parser.error("Provide either --target or --input")

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
