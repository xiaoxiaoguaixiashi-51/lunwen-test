"""LLM 客户端封装，兼容 OpenAI 格式的 API（DeepSeek、vLLM 等）。"""

from pathlib import Path


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
        self.client = OpenAI(
            base_url=llm_config["base_url"],
            api_key=llm_config["api_key"],
        )
        self.model = llm_config["model"]
        self.temperature = llm_config.get("temperature", 0.2)
        self.max_tokens = llm_config.get("max_tokens", 4096)

    def chat(self, messages: list[dict], temperature: float = None, max_tokens: int = None) -> str:
        """发送聊天请求，返回助手回复文本。"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        if content.strip():
            return content

        reasoning = getattr(choice.message, "reasoning_content", None) or ""
        finish_reason = getattr(choice, "finish_reason", "unknown")
        raise RuntimeError(
            "LLM returned empty message content "
            f"(finish_reason={finish_reason}, reasoning_preview={reasoning[:200]!r}). "
            "Use a non-reasoning chat model or increase max_tokens."
        )

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """便捷方法：system + user 消息组合。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages, **kwargs)
