"""PlanAgent：根据依赖分析结果生成测试计划。"""

import json
from src.core.llm_client import LLMClient


SYSTEM_PROMPT = """你是一个 Java 单元测试设计专家。你的任务是根据目标方法的依赖分析结果，设计完整的测试计划。

测试计划应包含：
1. 测试场景列表（覆盖正常路径、异常路径、边界条件）
2. 每个场景的 mock 策略（哪些依赖需要 mock，mock 返回什么）
3. 每个场景的断言策略（验证什么：返回值、异常、状态变化、交互）
4. 测试优先级

设计原则：
- 使用等价类划分和边界值分析
- 优先覆盖高风险路径
- 确保依赖隔离完整
- 断言要有意义，不只是 assertNotNull

输出 JSON 格式的测试计划。"""


USER_PROMPT_TEMPLATE = """## 依赖分析结果

```json
{dependency_analysis}
```

## 源代码

```java
{source_code}
```

请生成测试计划，JSON 格式如下：
{{
  "test_class_name": "XxxTest",
  "setup": {{
    "mocks": ["需要 mock 的依赖列表"],
    "fixtures": ["需要准备的测试数据"]
  }},
  "test_cases": [
    {{
      "name": "test_xxx",
      "scenario": "场景描述",
      "inputs": {{"参数名": "值"}},
      "mock_setup": [{{"target": "对象", "method": "方法", "returns": "返回值"}}],
      "assertions": [{{"type": "assertEquals/assertThrows/verify", "expected": "预期"}}],
      "priority": "high/medium/low"
    }}
  ]
}}"""


class PlanAgent:
    """根据依赖分析生成结构化测试计划。"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def generate_plan(self, dependency_analysis: dict, source_code: str) -> dict:
        """生成测试计划。"""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            dependency_analysis=json.dumps(dependency_analysis, indent=2, ensure_ascii=False),
            source_code=source_code,
        )

        response = self.llm.generate(SYSTEM_PROMPT, user_prompt)
        return self._parse_plan(response)

    def _parse_plan(self, response: str) -> dict:
        """从 LLM 回复中提取测试计划 JSON。"""
        if "```json" in response:
            start = response.index("```json") + 7
            end = response.index("```", start)
            json_str = response[start:end].strip()
        elif "```" in response:
            start = response.index("```") + 3
            end = response.index("```", start)
            json_str = response[start:end].strip()
        else:
            json_str = response.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"raw_response": response, "parse_error": True}
