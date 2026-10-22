"""RAG+LLM baseline runner for batch Java test generation.

This runner is intentionally separate from ``batch_runner`` and ``Pipeline``.
It performs a simple retrieval step over nearby project Java files, prompts the
LLM once, and saves the generated JUnit test class. It does not use TaskAgent,
PlanAgent, StaticGuard, Java6Guard, or compilation feedback repair.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from src.core.llm_client import LLMClient, load_config, trace_target
from src.utils.llm_output import extract_fenced_block
from src.utils.experiment_metadata import sha256_file


SYSTEM_PROMPT = """You are a Java unit test generation assistant used as a RAG+LLM baseline.
Generate one complete JUnit 4 test class for the requested target method.

Rules:
1. Use only JUnit 4 APIs such as org.junit.Test and org.junit.Assert.*.
2. Do not use JUnit 5/Jupiter APIs.
3. Use the retrieved source context when it helps with constructors, constants, and helper APIs.
4. Output only a complete Java file. Do not include explanations.
"""


USER_PROMPT_TEMPLATE = """## Target

File: {target_file}
Method: {method_name}

## Retrieved Source Context

{retrieved_context}

Generate a complete JUnit 4 test class for the target method.
"""


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CLASS_PATTERN = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b")
PUBLIC_CLASS_PATTERN = re.compile(r"\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b")


@dataclass
class RetrievedFile:
    path: Path
    score: int
    text: str


@dataclass
class BaselineResult:
    target_file: str
    method_name: str
    retrieved_files: list[str]
    generated_test: str
    success: bool

    def to_dict(self) -> dict:
        return {
            "target_file": self.target_file,
            "method_name": self.method_name,
            "retrieved_files": self.retrieved_files,
            "generated_test_length": len(self.generated_test),
            "success": self.success,
            "baseline": "rag_llm",
        }


def load_method_list(method_list_path: str) -> list[dict]:
    path = Path(method_list_path)
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Method list must be a JSON array")

    required = {"id", "target", "method"}
    for index, item in enumerate(items):
        missing = required - set(item)
        if missing:
            raise ValueError(f"Method list item #{index} is missing fields: {sorted(missing)}")
        if item.get("source_sha256") and sha256_file(item["target"]) != item["source_sha256"]:
            raise ValueError(f"Frozen source hash mismatch for {item['id']}")
    return items


def java6_guard_is_enabled() -> bool:
    return os.environ.get("LUNWEN_ENABLE_JAVA6_GUARD", "").lower() in {"1", "true", "yes", "on"}


def ensure_java6_guard_disabled():
    if java6_guard_is_enabled():
        raise RuntimeError(
            "Refusing to run RAG+LLM baseline while LUNWEN_ENABLE_JAVA6_GUARD is enabled. "
            "Unset it first so the baseline is not contaminated by the Ours Java6Guard."
        )


def infer_source_root(target_file: Path) -> Path:
    parts = list(target_file.resolve().parts)
    marker = ["src", "main", "java"]
    for index in range(0, len(parts) - len(marker) + 1):
        if [part.lower() for part in parts[index:index + len(marker)]] == marker:
            return Path(*parts[:index + len(marker)])
    return target_file.resolve().parent


def retrieve_source_context(
    target_file: Path,
    method_name: str,
    max_files: int = 6,
    max_chars: int = 24000,
) -> list[RetrievedFile]:
    source_root = infer_source_root(target_file)
    target_text = target_file.read_text(encoding="utf-8")
    query_tokens = tokenize(" ".join([target_file.stem, method_name, target_text]))

    retrieved: list[RetrievedFile] = [RetrievedFile(target_file, 10**9, target_text)]
    candidates = sorted(path for path in source_root.rglob("*.java") if path.resolve() != target_file.resolve())
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        score = score_text(text, query_tokens)
        if score > 0:
            retrieved.append(RetrievedFile(path, score, text))

    retrieved = [retrieved[0]] + sorted(retrieved[1:], key=lambda item: (-item.score, str(item.path)))
    return trim_retrieved_files(retrieved[:max_files], max_chars=max_chars)


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text) if len(token) > 2}


def score_text(text: str, query_tokens: set[str]) -> int:
    text_tokens = tokenize(text)
    return len(query_tokens & text_tokens)


def trim_retrieved_files(files: list[RetrievedFile], max_chars: int) -> list[RetrievedFile]:
    remaining = max_chars
    trimmed: list[RetrievedFile] = []
    for item in files:
        if remaining <= 0:
            break
        text = item.text[:remaining]
        trimmed.append(RetrievedFile(item.path, item.score, text))
        remaining -= len(text)
    return trimmed


def format_retrieved_context(files: list[RetrievedFile]) -> str:
    blocks = []
    for item in files:
        blocks.append(f"### {item.path}\n\n```java\n{item.text}\n```")
    return "\n\n".join(blocks)


class RagLlmBaselineRunner:
    def __init__(
        self,
        llm_client=None,
        max_context_files: int = 6,
        max_context_chars: int = 24000,
    ):
        self.llm = llm_client or LLMClient()
        self.max_context_files = max_context_files
        self.max_context_chars = max_context_chars

    def run_one(self, target_file: str, method_name: str, output_dir: str, *,
                method_owner: str = None, method_parameter_types: list[str] = None) -> BaselineResult:
        ensure_java6_guard_disabled()
        target_path = Path(target_file)
        source_files = retrieve_source_context(
            target_path,
            method_name,
            max_files=self.max_context_files,
            max_chars=self.max_context_chars,
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(
            target_file=target_file,
            method_name=method_name,
            retrieved_context=format_retrieved_context(source_files),
        )
        if method_owner:
            user_prompt += (
                "\nExact target declaring type: " + method_owner.replace("$", ".")
                + "\nExact target parameter types: " + json.dumps(method_parameter_types)
                + "\nGenerate tests for this declaration, not same-named methods in other classes.\n"
            )
        response = self.llm.generate(SYSTEM_PROMPT, user_prompt, max_tokens=8192)
        generated_test = extract_fenced_block(response, "java")
        self._save_results(target_path, method_name, source_files, generated_test, output_dir)
        return BaselineResult(
            target_file=target_file,
            method_name=method_name,
            retrieved_files=[str(item.path) for item in source_files],
            generated_test=generated_test,
            success=bool(generated_test.strip()),
        )

    def _save_results(
        self,
        target_file: Path,
        method_name: str,
        source_files: list[RetrievedFile],
        generated_test: str,
        output_dir: str,
    ):
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        class_name = extract_public_class_name(generated_test) or f"{extract_class_name(target_file) or method_name}Test"
        if not class_name.endswith("Test"):
            class_name = f"{class_name}Test"
        (out_path / f"{class_name}.java").write_text(generated_test, encoding="utf-8")
        report = {
            "baseline": "rag_llm",
            "target_file": str(target_file),
            "method_name": method_name,
            "retrieved_files": [str(item.path) for item in source_files],
            "generated_test_length": len(generated_test),
        }
        (out_path / f"{method_name}_rag_llm_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def extract_public_class_name(java_code: str) -> str:
    match = PUBLIC_CLASS_PATTERN.search(java_code)
    return match.group(1) if match else ""


def extract_class_name(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem
    match = CLASS_PATTERN.search(text)
    return match.group(1) if match else path.stem


def run_batch(
    methods: list[dict],
    output_dir: str,
    runner: RagLlmBaselineRunner,
    resume: bool = True,
) -> dict:
    ensure_java6_guard_disabled()
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary = {
        "baseline": "rag_llm",
        "total": len(methods),
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "items": [],
    }

    for item in methods:
        method_id = item["id"]
        item_dir = root / method_id
        status_file = item_dir / "status.json"
        if resume and status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            if status.get("status") == "completed":
                summary["skipped"] += 1
                summary["items"].append({"id": method_id, "status": "skipped"})
                continue

        item_dir.mkdir(parents=True, exist_ok=True)
        try:
            selector = {}
            if item.get("method_owner"):
                selector = {"method_owner": item["method_owner"],
                            "method_parameter_types": item.get("method_parameter_types")}
            with trace_target(method_id):
                result = runner.run_one(item["target"], item["method"], str(item_dir), **selector)
            status = {
                "id": method_id,
                "target": item["target"],
                "method": item["method"],
                "status": "completed" if result.success else "failed",
                "success": result.success,
                "baseline": "rag_llm",
                "retrieved_files": result.retrieved_files,
            }
            if result.success:
                summary["completed"] += 1
            else:
                summary["failed"] += 1
        except Exception as exc:
            status = {
                "id": method_id,
                "target": item["target"],
                "method": item["method"],
                "status": "error",
                "success": False,
                "baseline": "rag_llm",
                "error": str(exc),
            }
            summary["failed"] += 1

        status_file.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["items"].append(status)

    (root / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run RAG+LLM baseline batch generation")
    parser.add_argument("--methods", required=True, help="JSON method list")
    parser.add_argument("--output", required=True, help="Baseline output directory")
    parser.add_argument("--config", default=None, help="Config file path")
    parser.add_argument("--no-resume", action="store_true", help="Rerun completed items")
    parser.add_argument("--max-context-files", type=int, default=6, help="Maximum retrieved Java files per method")
    parser.add_argument("--max-context-chars", type=int, default=24000, help="Maximum retrieved context characters")
    args = parser.parse_args()
    os.environ.setdefault("KCF_LLM_TRACE_PATH", str(Path(args.output).resolve() / "llm_calls.jsonl"))
    os.environ.setdefault("KCF_EXPERIMENT_STAGE", "rag_llm_generation")

    ensure_java6_guard_disabled()
    methods = load_method_list(args.methods)
    config = load_config(args.config)
    runner = RagLlmBaselineRunner(
        LLMClient(config),
        max_context_files=args.max_context_files,
        max_context_chars=args.max_context_chars,
    )
    summary = run_batch(methods, args.output, runner, resume=not args.no_resume)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
