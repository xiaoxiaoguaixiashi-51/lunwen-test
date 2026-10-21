"""Lightweight dependency-construction knowledge retrieval.

This module is a local, deterministic first step toward the KG/LightRAG route:
knowledge is stored as JSONL records, retrieved lexically, and injected into the
planning stage. It is intentionally opt-in so historical Ours-v2 and baselines
remain unchanged unless KG/LightRAG is enabled.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DEFAULT_KNOWLEDGE_PATH = Path("experiments/knowledge/dependency_construction_knowledge.jsonl")


def kg_lightrag_enabled() -> bool:
    return os.environ.get("LUNWEN_ENABLE_KG_LIGHTRAG", "").lower() in {"1", "true", "yes", "on"}


def load_knowledge_records(path: str | Path = DEFAULT_KNOWLEDGE_PATH) -> list[dict[str, Any]]:
    record_path = Path(path)
    if not record_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(record_path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid knowledge JSONL at {record_path}:{line_number}") from exc
        if "id" not in record:
            raise ValueError(f"Knowledge record missing id at {record_path}:{line_number}")
        records.append(record)
    return records


def retrieve_dependency_knowledge(
    dependency_analysis: dict,
    source_code: str,
    method_name: str,
    knowledge_path: str | Path = DEFAULT_KNOWLEDGE_PATH,
    max_examples: int = 3,
) -> list[dict[str, Any]]:
    records = load_knowledge_records(knowledge_path)
    if not records or max_examples <= 0:
        return []

    query = build_query_text(dependency_analysis, source_code, method_name)
    query_tokens = tokenize(query)
    scored = []
    for record in records:
        score = score_record(record, query_tokens, method_name, dependency_analysis)
        if score > 0:
            scored.append((score, record.get("id", ""), record))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [compact_record(record, score) for score, _, record in scored[:max_examples]]


def build_query_text(dependency_analysis: dict, source_code: str, method_name: str) -> str:
    static = dependency_analysis.get("static_analysis", {}) if isinstance(dependency_analysis, dict) else {}
    llm_analysis = dependency_analysis.get("llm_analysis", {}) if isinstance(dependency_analysis, dict) else {}
    pieces: list[str] = [
        method_name,
        static.get("class_name", ""),
        static.get("method_name", ""),
        static.get("return_type", ""),
        " ".join(static.get("imports", []) or []),
        json.dumps(static.get("parameters", []), ensure_ascii=False),
        json.dumps(static.get("external_calls", []), ensure_ascii=False),
        json.dumps(static.get("field_dependencies", []), ensure_ascii=False),
        json.dumps(static.get("exceptions_thrown", []), ensure_ascii=False),
        json.dumps(llm_analysis, ensure_ascii=False),
        source_code[:12000],
    ]
    return "\n".join(piece for piece in pieces if piece)


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text) if len(token) > 2}


def score_record(record: dict[str, Any], query_tokens: set[str], method_name: str, dependency_analysis: dict) -> int:
    record_text = json.dumps(record, ensure_ascii=False)
    record_tokens = tokenize(record_text)
    score = len(query_tokens & record_tokens)

    static = dependency_analysis.get("static_analysis", {}) if isinstance(dependency_analysis, dict) else {}
    class_name = str(static.get("class_name", "")).lower()
    record_class = str(record.get("class", "")).lower()
    record_method = str(record.get("method", "")).lower()

    if class_name and class_name in record_class:
        score += 12
    if method_name and method_name.lower() == record_method:
        score += 20
    elif method_name and method_name.lower() in record_tokens:
        score += 6
    return score


def compact_record(record: dict[str, Any], score: int) -> dict[str, Any]:
    fields = [
        "id",
        "project",
        "class",
        "method",
        "dependency_types",
        "problem",
        "test_strategy",
        "assertion_strategy",
        "pitfalls",
        "example",
    ]
    compact = {field: record.get(field) for field in fields if field in record}
    compact["retrieval_score"] = score
    return compact


def knowledge_ids(records: list[dict[str, Any]]) -> list[str]:
    return [str(record.get("id", "")) for record in records if record.get("id")]
