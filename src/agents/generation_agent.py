"""GenerationAgent：根据测试计划生成 Java 单元测试代码。"""

import json
from src.core.llm_client import LLMClient
from src.utils.llm_output import extract_fenced_block


JUNIT5_SYSTEM_PROMPT = """你是一个 Java 单元测试代码生成专家。你的任务是根据测试计划生成可编译、可运行的 JUnit 5 测试代码。

代码要求：
1. 使用 JUnit 5 + Mockito 框架
2. 所有 import 必须完整且正确
3. Mock 对象使用 @Mock 注解 + @ExtendWith(MockitoExtension.class)
4. 每个测试方法对应测试计划中的一个场景
5. 断言要具体、有意义
6. 代码风格清晰，有必要的注释
7. 必须输出完整文件：所有 import、类声明、字段、setUp、测试方法和结尾大括号都不能省略

只输出完整的 Java 测试类代码。不要输出解释文字，不要省略任何 import、方法体或结尾大括号。"""


JUNIT4_SYSTEM_PROMPT = """你是一个 Java 单元测试代码生成专家。你的任务是根据测试计划生成可编译、可运行的 JUnit 4 测试代码。

代码要求：
1. 使用 JUnit 4，不要使用 JUnit 5/Jupiter
2. 只能使用 org.junit.Test、org.junit.Before、org.junit.Assert.* 等 JUnit 4 API
3. 禁止 import org.junit.jupiter.api.*、org.junit.jupiter.params.*、org.junit.jupiter.api.extension.*
4. 如需 Mockito，使用 MockitoJUnitRunner 或 MockitoAnnotations.initMocks(this)，不要使用 @ExtendWith
5. 每个测试方法对应测试计划中的一个场景
6. 断言要具体、有意义
7. 必须输出完整文件：所有 import、类声明、字段、setUp、测试方法和结尾大括号都不能省略

只输出完整的 Java 测试类代码。不要输出解释文字，不要省略任何 import、方法体或结尾大括号。"""


DEFECTS4J_JAVA6_COMPATIBILITY_PROMPT = """
Defects4J Lang-1b compatibility requirements:
1. Generate Java 6 source-compatible JUnit 4 code.
2. Do not use diamond operators such as new HashMap<>() or new ArrayList<>().
3. Do not use lambdas, method references, var, try-with-resources, multi-catch, or JUnit 5 APIs.
4. Use explicit generic types, for example new HashMap<String, Object>().
5. Prefer simple loops and anonymous classes when needed.
"""


USER_PROMPT_TEMPLATE = """## 测试框架

{test_framework}

## 测试计划

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

请生成完整的 {test_framework} 测试类代码。要求：
1. 所有 import 完整
2. 使用 Mockito mock 所有外部依赖
3. 每个测试场景一个 @Test 方法
4. 断言具体且有意义
5. 代码可直接编译运行
6. 只输出一个完整 Java 文件，不要解释，不要截断，不要使用省略号
7. 最后一行必须闭合测试类的右大括号
8. 如果测试框架是 JUnit 4，禁止使用 org.junit.jupiter.api 或 @ExtendWith"""


class GenerationAgent:
    """根据测试计划生成 Java 单元测试代码。"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def generate(
        self,
        test_plan: dict,
        source_code: str,
        dependency_info: dict,
        source_file: str = None,
    ) -> str:
        """生成测试代码。"""
        system_prompt, test_framework = self._prompts_for_source(source_file)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            test_framework=test_framework,
            test_plan=json.dumps(test_plan, indent=2, ensure_ascii=False),
            source_code=source_code,
            dependency_info=json.dumps(dependency_info, indent=2, ensure_ascii=False),
        )

        response = self.llm.generate(system_prompt, user_prompt, max_tokens=8192)
        return self._extract_code(response)

    def fix_compilation_error(
        self,
        test_code: str,
        error_message: str,
        source_code: str,
        source_file: str = None,
    ) -> str:
        """根据编译错误修复测试代码。"""
        system_prompt, test_framework = self._prompts_for_source(source_file)
        fix_prompt = f"""以下 Java 测试代码编译失败，请修复。

## 测试框架

{test_framework}

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
6. 最后一行必须闭合测试类的右大括号
7. 如果测试框架是 JUnit 4，必须移除 org.junit.jupiter.api、org.junit.jupiter.params 和 @ExtendWith"""

        response = self.llm.generate(system_prompt, fix_prompt, max_tokens=8192)
        return self._extract_code(response)

    def _extract_code(self, response: str) -> str:
        """从 LLM 回复中提取 Java 代码。"""
        return extract_fenced_block(response, "java")

    def _prompts_for_source(self, source_file: str = None) -> tuple[str, str]:
        """Select test framework guidance from the target project context."""
        if source_file and self._looks_like_defects4j(source_file):
            return JUNIT4_SYSTEM_PROMPT + "\n" + DEFECTS4J_JAVA6_COMPATIBILITY_PROMPT, "JUnit 4"
        return JUNIT5_SYSTEM_PROMPT, "JUnit 5"

    def _looks_like_defects4j(self, source_file: str) -> bool:
        normalized = source_file.replace("\\", "/").lower()
        return "/defects4j-work/" in normalized or "/defects4j/" in normalized
