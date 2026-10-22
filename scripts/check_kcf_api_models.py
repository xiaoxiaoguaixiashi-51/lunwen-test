"""Check configured model against authenticated model listing; no generation."""

import argparse
import json
from pathlib import Path

import yaml
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))["llm"]
    try:
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"],
                        timeout=30, max_retries=0)
        ids = sorted(model.id for model in client.models.list().data)
    except Exception as exc:
        # Never echo exception bodies, headers or private config contents.
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "status_code": getattr(exc, "status_code", None)}))
        return 2
    found = config["model"] in ids
    print(json.dumps({"configured_model": config["model"], "available_models": ids,
                      "configured_model_listed": found,
                      "generation_requests_sent": 0}, ensure_ascii=False))
    return 0 if found else 3


if __name__ == "__main__":
    raise SystemExit(main())
