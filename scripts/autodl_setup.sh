#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

WRITE_CONFIG=0
if [[ "${1:-}" == "--write-config" ]]; then
  WRITE_CONFIG=1
fi

echo "[1/5] Installing system dependencies..."
if command -v apt >/dev/null 2>&1; then
  apt update
  apt install -y git python3 python3-venv python3-pip openjdk-17-jdk maven unzip curl tmux
else
  echo "apt not found. Please install git, python3, openjdk-17-jdk, maven, unzip, curl, tmux manually." >&2
fi

echo "[2/5] Creating Python virtual environment..."
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "[3/5] Installing Python requirements..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "[4/5] Preparing config..."
if [[ ! -f "config/config.yaml" ]]; then
  cp config/config.example.yaml config/config.yaml
  echo "Created config/config.yaml from example."
fi

if [[ "$WRITE_CONFIG" == "1" ]]; then
  if [[ -z "${LLM_BASE_URL:-}" || -z "${LLM_API_KEY:-}" || -z "${LLM_MODEL:-}" ]]; then
    echo "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL must be set before --write-config." >&2
    echo "Example:" >&2
    echo "  export LLM_BASE_URL='https://api.example.com/v1'" >&2
    echo "  export LLM_API_KEY='sk-...'" >&2
    echo "  export LLM_MODEL='deepseek-coder-v2'" >&2
    exit 1
  fi

  python - <<'PY'
import os
from pathlib import Path

config = f"""# LLM API
llm:
  base_url: "{os.environ['LLM_BASE_URL']}"
  api_key: "{os.environ['LLM_API_KEY']}"
  model: "{os.environ['LLM_MODEL']}"
  temperature: 0.2
  max_tokens: 4096

# Java environment
java:
  home: ""
  compile_timeout: 30
  test_timeout: 60

# Pipeline
pipeline:
  max_fix_iterations: 3
  feedback_enabled: true
"""
Path("config/config.yaml").write_text(config, encoding="utf-8")
PY
  echo "Wrote config/config.yaml from environment variables."
else
  echo "Skipped API config write. Use --write-config after setting LLM_BASE_URL, LLM_API_KEY, LLM_MODEL."
fi

echo "[5/5] Versions:"
python --version
java -version
mvn -version

echo "AutoDL setup completed."
