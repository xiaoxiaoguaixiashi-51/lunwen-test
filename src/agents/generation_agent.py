"""GenerationAgent：根据测试计划生成 Java 单元测试代码。"""

import json
from src.core.llm_client import LLMClient
from src.utils.llm_output import extract_fenced_block


SYSTEM_PROMPT = """你是一个 Java 单元测试代码生成专家。你的任务是根据测试计划生成可编译、可运行的 JUnit 5 测试代码。

代码要求：
1. 使用 JUnit 5 + Mockito 框架
2. 所有 import 必须完整且正确
3. Mock 对象使用 @Mock 注解 + @ExtendWith(MockitoExtension.class)
4. 每个测试方法对应测试计划中的一个场景
5. 断言要具体、有意义
6. 代码风格清晰，有必要的注释
7. 必须输出完整文件：所有 import、类声明、字段、setUp、测试方法和结尾大括号都不能省略

只输出完整的 Java 测试类代码。不要输出解释文字，不要省略任何 import、方法体或结尾大括号。"""


USER_PROMPT_TEMPLATE = """## 测试计划

```json
{test_plan}
```

## 被测源代码

```java
{source_code}
```

## 依赖分析

```json
{dependency_info}
```

请生成完整的 JUnit 5 测试类代码。要求：
1. 所有 import 完整
2. 使用 Mockito mock 所有外部依赖
3. 每个测试场景一个 @Test 方法
4. 断言具体且有意义
5. 代码可直接编译运行
6. 只输出一个完整 Java 文件，不要解释，不要截断，不要使用省略号
7. 最后一行必须闭合测试类的右大括号"""


class GenerationAgent:
    """根据测试计划生成 Java 单元测试代码。"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def generate(self, test_plan: dict, source_code: str, dependency_info: dict) -> str:
        """生成测试代码。"""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            test_plan=json.dumps(test_plan, indent=2, ensure_ascii=False),
            source_code=source_code,
            dependency_info=json.dumps(dependency_info, indent=2, ensure_ascii=False),
        )

        response = self.llm.generate(SYSTEM_PROMPT, user_prompt, max_tokens=8192)
        return self._extract_code(response)

    def fix_compilation_error(self, test_code: str, error_message: str, source_code: str) -> str:
        """根据编译错误修复测试代码。"""
        fix_prompt = f"""以下 Java 测试代码编译失败，请修复。

## 当前测试代码

```java
{test_code}
```

## 编译错误

```
{error_message}
```

## 被测源代码

```java
{source_code}
```

请输出修复后的完整测试代码。注意：
1. 修复所有编译错误
2. 确保 import 完整
3. 确保类型匹配
4. 不要改变测试逻辑，只修复编译问题
5. 只输出一个完整 Java 文件，不要解释，不要截断，不要使用省略号
6. 最后一行必须闭合测试类的右大括号"""

        response = self.llm.generate(SYSTEM_PROMPT, fix_prompt, max_tokens=8192)
        return self._extract_code(response)

    def _extract_code(self, response: str) -> str:
        """从 LLM 回复中提取 Java 代码。"""
        return extract_fenced_block(response, "java")
