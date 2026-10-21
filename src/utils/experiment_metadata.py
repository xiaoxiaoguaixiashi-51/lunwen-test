"""Helpers for recording reproducible experiment settings without secrets."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


SECRET_KEYS = {"api_key", "secret", "token", "password"}


def sha256_file(path: str | Path) -> str | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in SECRET_KEYS else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def git_revision(cwd: str | Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def write_run_metadata(
    output_dir: str | Path,
    *,
    stage: str,
    method_list: str | Path,
    config_path: str | Path | None,
    config: dict,
    settings: dict,
    knowledge_path: str | Path | None = None,
    inputs: dict | None = None,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "stage": stage,
        "repository_revision": git_revision(Path(__file__).resolve().parents[2]),
        "method_list": str(method_list),
        "method_list_sha256": sha256_file(method_list),
        "config_path": str(config_path) if config_path else None,
        "config_sha256": sha256_file(config_path) if config_path else None,
        "config_redacted": redact_secrets(config),
        "knowledge_path": str(knowledge_path) if knowledge_path else None,
        "knowledge_sha256": sha256_file(knowledge_path) if knowledge_path else None,
        "effective_settings": settings,
        "inputs": inputs or {},
    }
    target = output / "run_metadata.json"
    target.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
