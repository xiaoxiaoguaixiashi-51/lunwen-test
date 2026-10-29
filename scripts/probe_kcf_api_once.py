"""Check saved settings; send one tiny request only with --send-once. Never retry."""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core.llm_client import LLMClient, load_config


def safe_settings(config):
    llm = config["llm"]
    parsed = urlsplit(llm["base_url"])
    if (parsed.scheme != "https" or parsed.hostname != "api.deepseek.com" or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.port not in (None, 443) or parsed.path not in ("", "/", "/v1", "/v1/")):
        raise ValueError("Expected saved official DeepSeek HTTPS endpoint")
    if not llm.get("api_key") or llm["api_key"] == "your-api-key":
        raise ValueError("Private key missing or placeholder")
    if llm.get("model") != "deepseek-flash" or llm.get("thinking") != "disabled":
        raise ValueError("Saved model/thinking differs from expected diagnostic settings")
    return {"endpoint_host": parsed.hostname, "model": llm["model"], "thinking": llm["thinking"],
            "temperature": llm.get("temperature", 0.2), "key_present": True,
            "probe_max_tokens": 16, "probe_timeout_seconds": 30, "probe_max_retries": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--send-once", action="store_true")
    args = parser.parse_args()
    if not args.config.is_file():
        raise FileNotFoundError("Exact private configuration missing; no fallback allowed")
    config = load_config(str(args.config))
    settings = safe_settings(config)
    if not args.send_once:
        print(json.dumps({"settings": settings, "api_calls": 0}))
        return
    if args.output_dir is None:
        parser.error("--send-once requires a fresh --output-dir")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    # Persistent intent record prevents accidental reuse of this probe output directory.
    summary = {"kind": "api_connectivity_probe_not_experiment", "settings": settings,
               "requests_planned": 1, "status": "started", "cost_amount": None,
               "cost_note": "usage recorded; monetary charge not independently verified"}
    path = args.output_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    config["llm"].update(max_retries=0, timeout=30, max_tokens=16)
    os.environ["KCF_LLM_TRACE_PATH"] = str(args.output_dir / "llm_calls.jsonl")
    os.environ["KCF_EXPERIMENT_STAGE"] = "connectivity_probe_20261030"
    try:
        client = LLMClient(config)
        response = client.generate("Reply with OK only.", "Connection check.", max_tokens=16)
        summary.update(status="ok", reply_matches_ok=response.strip() == "OK")
    except Exception as exc:
        # Do not expose provider body, config or exception message.
        summary.update(status="error", error_type=type(exc).__name__, status_code=getattr(exc, "status_code", None))
    trace = args.output_dir / "llm_calls.jsonl"
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()] if trace.exists() else []
    summary["recorded_calls"] = len(events)
    if events:
        summary.update(usage=events[-1]["usage"], elapsed_seconds=events[-1]["elapsed_seconds"],
                       response_model=events[-1].get("response_model"))
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    if summary["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
