"""LLM 客户端封装，兼容 OpenAI 格式的 API（DeepSeek、vLLM 等）。"""

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

TRACE_LOCK = threading.Lock()
TRACE_TARGET = ContextVar("kcf_trace_target", default=None)


@contextmanager
def trace_target(target_id: str):
    token = TRACE_TARGET.set(target_id)
    try:
        yield
    finally:
        TRACE_TARGET.reset(token)


def load_config(config_path: str = None) -> dict:
    """加载配置文件。"""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load config files. Run: pip install -r requirements.txt") from exc

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        # 尝试加载 example 配置
        example_path = config_path.parent / "config.example.yaml"
        if example_path.exists():
            config_path = example_path
        else:
            raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class LLMClient:
    """封装 LLM API 调用，兼容 OpenAI 格式。"""

    def __init__(self, config: dict = None):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai is required for real LLM calls. Run: pip install -r requirements.txt") from exc

        if config is None:
            config = load_config()

        llm_config = config["llm"]
        options = {key: llm_config[key] for key in ("max_retries", "timeout") if key in llm_config}
        self.client = OpenAI(
            base_url=llm_config["base_url"],
            api_key=llm_config["api_key"],
            **options,
        )
        self.model = llm_config["model"]
        self.temperature = llm_config.get("temperature", 0.2)
        self.max_tokens = llm_config.get("max_tokens", 4096)
        self.thinking = llm_config.get("thinking")
        if self.thinking is not None and self.thinking not in {"enabled", "disabled"}:
            raise ValueError("llm.thinking must be enabled or disabled")
        self._trace_secret = llm_config["api_key"]
        self.trace_path = os.environ.get("KCF_LLM_TRACE_PATH")
        if self.trace_path:
            Path(self.trace_path).parent.mkdir(parents=True, exist_ok=True)
        self.max_retries = llm_config.get("max_retries", "sdk_default")

    def chat(self, messages: list[dict], temperature: float = None, max_tokens: int = None) -> str:
        """发送聊天请求，返回助手回复文本。"""
        request = {"model": self.model, "messages": messages,
                   "temperature": self.temperature if temperature is None else temperature,
                   "max_tokens": self.max_tokens if max_tokens is None else max_tokens}
        if self.thinking is not None:
            request["extra_body"] = {"thinking": {"type": self.thinking}}
        event = {"call_id": uuid.uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
                 "target_id": TRACE_TARGET.get(),
                 "stage": os.environ.get("KCF_EXPERIMENT_STAGE"), "request": request,
                 "sdk_max_retries": self.max_retries}
        started = time.monotonic()
        response = None
        try:
            response = self.client.chat.completions.create(**request)
            choice = response.choices[0]
            content = choice.message.content or ""
            event.update(status="ok", response_model=getattr(response, "model", None),
                         response_text=content, finish_reason=getattr(choice, "finish_reason", None))
            if content.strip():
                return content
            raise RuntimeError("LLM returned empty message content; inspect finish_reason and token budget")
        except Exception as exc:
            event.update(status="error", error_type=type(exc).__name__,
                         status_code=getattr(exc, "status_code", None))
            raise
        finally:
            event["elapsed_seconds"] = round(time.monotonic() - started, 6)
            usage = getattr(response, "usage", None)
            event["usage"] = {key: getattr(usage, key, None) for key in (
                "prompt_tokens", "completion_tokens", "total_tokens",
                "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")}
            if self.trace_path:
                line = json.dumps(event, ensure_ascii=False)
                if self._trace_secret:
                    line = line.replace(self._trace_secret, "<redacted>")
                with TRACE_LOCK, Path(self.trace_path).open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """便捷方法：system + user 消息组合。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages, **kwargs)
