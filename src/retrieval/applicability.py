"""Conservative three-state checks for retrieved test knowledge."""

from __future__ import annotations

import json
import re
from typing import Any


SATISFIED = "satisfied"
CONFLICT = "conflict"
UNKNOWN = "unknown"


def _record_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False).lower()


def _positive_requirement(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        if phrase in text and not re.search(rf"(?:do not|avoid|without|禁止|不要).{{0,40}}{re.escape(phrase)}", text):
            return phrase
    return None


def assess_record(
    record: dict[str, Any],
    *,
    target_project: str = "",
    target_class: str = "",
    target_method: str = "",
    target_framework: str = "junit4",
    forbidden_libraries: tuple[str, ...] = ("mockito", "powermock", "junit5", "jupiter"),
    max_java_source: int = 8,
) -> dict[str, Any]:
    """Return a conservative status and evidence-based reasons.

    A record is never rejected merely because it comes from another project or
    mentions a class absent from the target. Those cases remain ``unknown``.
    """
    text = _record_text(record)
    reasons: list[str] = []

    forbidden_hits = []
    for library in forbidden_libraries:
        hit = _positive_requirement(text, (library,))
        if hit:
            forbidden_hits.append(hit)
    if forbidden_hits:
        reasons.append("explicit forbidden framework/library requirement: " + ", ".join(sorted(set(forbidden_hits))))
        return {"status": CONFLICT, "reasons": reasons}

    if target_framework.lower() == "junit4":
        junit5_hit = _positive_requirement(text, ("junit 5", "junit5", "jupiter", "org.junit.jupiter"))
        if junit5_hit:
            reasons.append(f"target requires JUnit 4 but record requires {junit5_hit}")
            return {"status": CONFLICT, "reasons": reasons}

    java_versions = [int(value) for value in re.findall(r"(?:java|source|target)[^\n]{0,12}?\b(?:1\.)?(\d{1,2})\b", text)]
    too_new = [value for value in java_versions if value > max_java_source]
    if too_new:
        reasons.append(f"record requires Java source level above {max_java_source}: {max(too_new)}")
        return {"status": CONFLICT, "reasons": reasons}

    project = str(record.get("project", ""))
    record_class = str(record.get("class", ""))
    record_method = str(record.get("method", ""))
    if target_project and project == target_project:
        reasons.append("record project matches target project")
        return {"status": SATISFIED, "reasons": reasons}
    if target_class and record_class == target_class:
        reasons.append("record class matches target class")
        return {"status": SATISFIED, "reasons": reasons}
    if target_method and record_method == target_method:
        reasons.append("record method matches target method")
        return {"status": SATISFIED, "reasons": reasons}

    reasons.append("no explicit conflict or target capability match was found")
    return {"status": UNKNOWN, "reasons": reasons}
