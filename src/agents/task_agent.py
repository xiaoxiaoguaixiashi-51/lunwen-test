"""TaskAgent：分析目标 Java 方法，识别依赖信息。"""

import json
from src.core.llm_client import LLMClient
from src.utils.java_parser import extract_dependencies, DependencyInfo
from src.utils.llm_output import extract_fenced_block
from pathlib import Path


SYSTEM_PROMPT = """你是一个 Java 代码依赖分析专家。你的任务是分析给定 Java 方法的依赖关系，输出结构化的依赖信息。

你需要识别以下依赖类型：
1. 外部方法调用（哪些对象的哪些方法被调用）
2. 字段依赖（使用了哪些类字段）
3. 构造依赖（对象如何被创建和注入）
4. 特殊依赖（时间、随机数、I/O、网络、数据库）
5. 异常路径（可能抛出的异常）

请基于 AST 分析结果和源代码，补充 AST 可能遗漏的语义信息。
输出 JSON 格式。"""


USER_PROMPT_TEMPLATE = """## 目标方法源代码

```java
{source_code}
```

## AST 静态分析结果

```json
{ast_analysis}
```

请补充分析以下内容，以 JSON 格式输出：
1. dependency_summary: 一句话总结该方法的依赖复杂度
2. mock_candidates: 哪些依赖在测试中需要 mock，以及 mock 策略
3. test_challenges: 测试该方法的主要挑战
4. suggested_test_scenarios: 建议的测试场景（至少 3 个）"""


class TaskAgent:
    """分析目标 Java 方法的依赖，为后续测试生成提供结构化信息。"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def analyze(self, java_file_path: str, method_name: str = None) -> dict:
        """分析目标方法，返回完整的依赖分析结果。"""
        # Step 1: AST 静态分析
        dep_info = extract_dependencies(java_file_path, method_name)

        # Step 2: 读取源代码
        source_code = Path(java_file_path).read_text(encoding="utf-8")

        # Step 3: LLM 补充语义分析
        user_prompt = USER_PROMPT_TEMPLATE.format(
            source_code=source_code,
            ast_analysis=json.dumps(dep_info.to_dict(), indent=2, ensure_ascii=False),
        )

        llm_response = self.llm.generate(SYSTEM_PROMPT, user_prompt)

        # Step 4: 合并结果
        result = {
            "static_analysis": dep_info.to_dict(),
            "llm_analysis": self._parse_llm_response(llm_response),
            "raw_llm_response": llm_response,
        }
        return result

    def _parse_llm_response(self, response: str) -> dict:
        """尝试从 LLM 回复中提取 JSON。"""
        json_str = extract_fenced_block(response, "json")

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"raw": response}
