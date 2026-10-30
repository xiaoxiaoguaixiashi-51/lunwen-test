"""Exercise real local tokenizer and shared budget with an SDK fake, never an API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core.llm_client import LLMClient, trace_target
from src.utils.request_budget import BudgetExceeded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.tokenizer_zip) as archive:
        raw = archive.read("deepseek_v4_tokenizer/tokenizer.json")
    tokenizer_path = root / "tokenizer.json"
    tokenizer_path.write_bytes(raw)
    policy = {"ledger_path": str(root / "budget.sqlite"), "tokenizer_json": str(tokenizer_path),
              "tokenizer_sha256": hashlib.sha256(raw).hexdigest(), "framing_reserve": 256,
              "max_calls_per_target": 1, "max_total_tokens_per_target": 20000,
              "max_input_tokens_per_call": 12000, "max_output_tokens_per_call": 16}
    config = {"llm": {"base_url": "https://example.invalid", "api_key": "offline-placeholder",
                      "model": "offline-test", "max_retries": 0}, "request_budget": policy}
    sdk = Mock()
    sdk.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="OK"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=13, completion_tokens=1, total_tokens=14))
    trace = root / "trace.jsonl"
    with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=Mock(return_value=sdk))}), patch.dict(os.environ, {
            "KCF_LLM_TRACE_PATH": str(trace), "KCF_EXPERIMENT_STAGE": "offline_initial"}), patch(
            "socket.socket", side_effect=AssertionError("Network forbidden")):
        first = LLMClient(config)
        with trace_target("fixed-method"):
            assert first.generate("Reply with OK only.", "Connection check.", max_tokens=8192) == "OK"
        # Reopen the persisted ledger, matching a new process/stage constructor.
        second = LLMClient(config)
        os.environ["KCF_EXPERIMENT_STAGE"] = "offline_feedback"
        blocked = False
        try:
            with trace_target("fixed-method"):
                second.generate("system", "feedback", max_tokens=8192)
        except BudgetExceeded:
            blocked = True
    assert blocked and sdk.chat.completions.create.call_count == 1
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert not events[-1]["provider_call_attempted"] and events[-1]["status"] == "budget_blocked"
    summary = {"kind": "offline_fake_sdk_real_tokenizer_smoke", "real_api_calls": 0, "fake_sdk_calls": 1,
               "cross_stage_second_call_blocked": True, "tokenizer_sha256": policy["tokenizer_sha256"],
               "effective_max_output": events[0]["request"]["max_tokens"],
               "estimated_input_with_reserve": events[0]["budget"]["estimated_input_with_reserve"],
               "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
