"""Static compatibility checks for generated Java tests."""

from __future__ import annotations

import re


JAVA6_PATTERNS: list[tuple[str, str]] = [
    (
        "diamond_operator",
        r"new\s+[A-Za-z_$][\w$]*(?:\s*\.[A-Za-z_$][\w$]*)*(?:\s*<[^>;=\n]+>)?\s*<\s*>",
    ),
    ("lambda_expression", r"->"),
    ("method_reference", r"::"),
    ("multi_catch", r"catch\s*\([^)]*\|[^)]*\)"),
    ("try_with_resources", r"try\s*\([^)]*(?:=|;)[^)]*\)"),
]


def java6_compatibility_errors(java_code: str) -> list[str]:
    """Return Java 6 source-level compatibility errors for generated tests."""
    errors: list[str] = []
    for name, pattern in JAVA6_PATTERNS:
        match = re.search(pattern, java_code)
        if match:
            errors.append(f"{name}: Java 6 / Defects4J Lang-1b does not support `{match.group(0)[:80]}`")
    return errors


def format_java6_compatibility_errors(java_code: str) -> str:
    errors = java6_compatibility_errors(java_code)
    if not errors:
        return ""
    lines = [
        "Generated test code is not Java 6 source-compatible for Defects4J Lang-1b.",
        "Rewrite the test using Java 6 syntax only.",
        "Do not use diamond operators, lambdas, method references, multi-catch, try-with-resources, var, or JUnit 5 APIs.",
    ]
    lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)
