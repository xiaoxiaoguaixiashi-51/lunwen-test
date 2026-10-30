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
from src.utils.request_budget import load_budget, BudgetExceeded
from src.utils.phase_trace import PARENT as PHASE_PARENT

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
        self.budget, self.count_budget_input = load_budget(config, self.model)
        if self.budget is not None and (self.max_retries != 0 or not self.trace_path):
            raise ValueError("Budgeted runs require max_retries=0 and KCF_LLM_TRACE_PATH")

    def chat(self, messages: list[dict], temperature: float = None, max_tokens: int = None) -> str:
        """发送聊天请求，返回助手回复文本。"""
        request = {"model": self.model, "messages": messages,
                   "temperature": self.temperature if temperature is None else temperature,
                   "max_tokens": self.max_tokens if max_tokens is None else max_tokens}
        requested_max_tokens = request["max_tokens"]
        if self.budget is not None:
            request["max_tokens"] = min(request["max_tokens"], self.budget.policy["max_output_tokens_per_call"])
        if self.thinking is not None:
            request["extra_body"] = {"thinking": {"type": self.thinking}}
        event = {"call_id": uuid.uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
                 "target_id": TRACE_TARGET.get(),
                 "phase_span_id": PHASE_PARENT.get(),
                 "stage": os.environ.get("KCF_EXPERIMENT_STAGE"), "request": request,
                 "sdk_max_retries": self.max_retries, "provider_call_attempted": False}
        started = time.monotonic()
        response = None
        reservation = None
        try:
            if self.budget is not None:
                reservation = self.budget.reserve(event["call_id"], event["target_id"], event["stage"],
                                                  self.count_budget_input(messages), request["max_tokens"])
                event["budget"] = {**reservation, "requested_max_output": requested_max_tokens}
            event["provider_call_attempted"] = True
            response = self.client.chat.completions.create(**request)
            choice = response.choices[0]
            content = choice.message.content or ""
            event.update(status="ok", response_model=getattr(response, "model", None),
                         response_id=getattr(response, "id", None),
                         system_fingerprint=getattr(response, "system_fingerprint", None),
                         response_text=content, finish_reason=getattr(choice, "finish_reason", None))
            if content.strip():
                return content
            raise RuntimeError("LLM returned empty message content; inspect finish_reason and token budget")
        except Exception as exc:
            event.update(status="budget_blocked" if isinstance(exc, BudgetExceeded) else "error", error_type=type(exc).__name__,
                         status_code=getattr(exc, "status_code", None))
            raise
        finally:
            event["elapsed_seconds"] = round(time.monotonic() - started, 6)
            usage = getattr(response, "usage", None)
            event["usage"] = {key: getattr(usage, key, None) for key in (
                "prompt_tokens", "completion_tokens", "total_tokens",
                "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")}
            if reservation is not None:
                event["budget_settlement"] = self.budget.settle(event["call_id"], event["usage"])
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
