"""Configure private cloud API settings interactively without echoing the key."""

from __future__ import annotations

import getpass
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / "config/private"
    if output.exists():
        raise FileExistsError("Private configuration already exists; it has not been overwritten")
    base_url = input("API base URL (for example https://provider.example/v1): ").strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Enter a complete HTTP(S) API base URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL must not contain credentials, query tokens, or fragments")
    model = input("Exact model ID: ").strip()
    key = getpass.getpass("API key (hidden; not written to GitHub): ").strip()
    if not model or not key:
        raise ValueError("Model ID and API key are required")
    configs = {}
    for variant, template in [("full", "config.kcf_utg.yaml"),
                               ("a1", "config.kcf_utg_a1.yaml"),
                               ("a3", "config.kcf_utg_a3.yaml")]:
        config = yaml.safe_load((root / "config" / template).read_text(encoding="utf-8"))
        config["llm"].update(base_url=base_url, model=model, api_key=key)
        config["java"]["home"] = "/usr/lib/jvm/java-8-openjdk-amd64"
        configs[variant] = config
    output.mkdir(mode=0o700)
    for variant, config in configs.items():
        target = output / f"kcf_{variant}.yaml"
        target.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        target.chmod(0o600)
    print("Private API configuration saved. No API request has been sent.")
    print("A2 and the independent RAG baseline use the same Full model settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
