#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -d ".venv" ]]; then
  echo ".venv not found. Run: bash scripts/autodl_setup.sh" >&2
  exit 1
fi

source .venv/bin/activate

echo "[1/7] Tool versions"
python --version
java -version
mvn -version

echo "[2/7] Python offline tests"
python -m unittest discover tests

echo "[3/7] Java Maven smoke"
pushd examples/java-demo >/dev/null
mvn test
popd >/dev/null

echo "[4/7] Checking config"
if [[ ! -f "config/config.yaml" ]]; then
  echo "config/config.yaml not found. Run setup and configure LLM API first." >&2
  exit 1
fi

echo "[5/7] Single-method pipeline smoke"
python -m src.core.pipeline \
  --target examples/java-demo/src/main/java/com/example/service/UserService.java \
  --method updateUserEmail \
  --output experiments/smoke

echo "[6/7] Batch runner smoke"
python -m src.core.batch_runner \
  --methods examples/method_lists/smoke.json \
  --output experiments/runs/smoke \
  --no-resume

echo "[7/7] Result check"
test -f experiments/runs/smoke/summary.json
find experiments/runs/smoke -name status.json -print

echo "AutoDL smoke completed."
