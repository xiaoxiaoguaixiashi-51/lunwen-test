# 高依赖复杂 Java 单元测试生成增强框架

基于依赖构造知识图谱和多智能体协作的 Java 单元测试自动生成工具。

## 核心创新

1. **依赖构造知识图谱 + LightRAG 检索** — 存储依赖如何 mock、构造、断言的经验
2. **DCCI 指标** — 衡量依赖构造复杂度，而非仅依赖数量
3. **增强型 3 Agent 架构** — 与 MACO 同构，但每个环节都有增强
4. **StaticGuard 符号约束** — 降低 LLM 符号幻觉
5. **LLM + EvoSuite 混合** — 互补优势

## 架构

```
目标 Java 方法
  ↓
TaskAgent（AST + LLM 语义补充 + 结构化依赖图谱）
  ↓
依赖构造知识图谱 + LightRAG 检索
  ↓
PlanAgent（LightRAG 检索 + 断言策略设计）
  ↓
EvoSuite 辅助输入搜索
  ↓
GenerationAgent（StaticGuard 符号校验 + 编译反馈修复）
  ↓
编译、运行、覆盖率、变异测试反馈
```

## 环境要求
- Python >= 3.10
- Java >= 11 (用于编译和运行生成的测试)
- Maven (用于管理 Java 依赖)

## 安装
```bash
pip install -r requirements.txt
```

## 配置
复制 `config/config.example.yaml` 为 `config/config.yaml`，填入 LLM API 配置（支持 OpenAI 兼容格式，如 DeepSeek）。

## 运行
```bash
python -m src.core.pipeline --target examples/target_methods/UserService.java --method updateUserEmail
```

## 本地离线测试

本地电脑先作为开发和小规模验证环境。离线测试不需要真实 LLM API、JDK 或 Maven：

```bash
python -m unittest discover tests
```

## Java smoke test

`examples/java-demo` 是一个最小 Maven 示例项目，用于本地或云端验证 Java/JUnit/Mockito 环境：

```bash
cd examples/java-demo
mvn test
```

pipeline 推荐使用该示例项目中的目标方法：

```bash
python -m src.core.pipeline --target examples/java-demo/src/main/java/com/example/service/UserService.java --method updateUserEmail
```

## 批量实验

批量运行入口支持方法列表、断点续跑和每个方法独立输出目录：

```bash
python -m src.core.batch_runner --methods examples/method_lists/smoke.json --output experiments/runs
```

云服务器部署步骤见 `docs/CLOUD_BEGINNER_GUIDE.md`。

## 项目结构
```
src/
├── agents/          # 3 个核心 Agent
│   ├── task_agent.py        # 依赖分析（AST + LLM 补充）
│   ├── plan_agent.py        # 测试计划生成（LightRAG 检索 + 断言策略）
│   └── generation_agent.py  # 测试代码生成（StaticGuard + 编译修复）
├── core/            # 核心调度与 pipeline
│   ├── pipeline.py          # 端到端流程编排
│   └── llm_client.py        # LLM 调用封装（OpenAI 兼容格式）
├── utils/           # 工具函数
│   ├── java_parser.py       # Java AST 解析（javalang）
│   ├── compiler.py          # 编译与运行
│   ├── static_guard.py      # 符号校验模块（待实现）
│   └── evosuite_wrapper.py  # EvoSuite 集成（待实现）
├── knowledge_graph/ # 依赖构造知识图谱（待实现）
├── retrieval/       # LightRAG 检索层（待实现）
└── metrics/         # DCCI 计算（待实现）
config/              # 配置文件
examples/            # 示例目标方法和生成结果
tests/               # 单元测试
docs/                # 云端部署和实验说明
```

## 论文

**Title:** Dependency-Aware Test Generation for Complex Java Methods via Knowledge Graph and Multi-Agent Collaboration

**核心贡献：**
- 依赖构造知识图谱（最大创新）
- DCCI 指标（方法学贡献）
- 增强型多智能体框架（3 Agent + 2 工具模块）
