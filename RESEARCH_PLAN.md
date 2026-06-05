# 研究计划：高依赖复杂 Java 单元测试生成增强方案

## 1. 研究出发点

本项目以 MACO 论文为基础，但不是简单复刻 MACO，而是在其多智能体单元测试生成框架上进一步改进。MACO 的核心流程是：TaskAgent 进行依赖分析，PlanAgent 生成测试计划，GenerationAgent 生成测试代码，并通过覆盖率反馈不断优化。

我们的目标是：面向高依赖复杂 Java 方法，构建一套更完整的测试生成增强框架，使系统不仅能生成测试代码，还能理解依赖、检索依赖处理经验、约束大模型符号幻觉、搜索有效输入、生成更有价值的断言，并通过反馈持续修复。

## 2. 核心创新点定位

### 主线创新（论文核心卖点）

1. **依赖构造知识图谱 + LightRAG 检索** — MACO 没有的最大创新
   - 不只存"依赖是什么"，还存"依赖怎么 mock、怎么构造、常见失败模式"
   - 多跳检索相似依赖链和历史修复经验

2. **DCCI 指标** — 方法学贡献
   - MACO 的 MDCI 只看依赖数量和深度
   - DCCI 看构造难度：是否难以构造、隔离、mock、断言

### 辅助创新（增强严谨性）

3. **StaticGuard 符号约束** — 降低 LLM 符号幻觉（漏 import、写错类名、混淆重载）
4. **LLM + EvoSuite 混合** — 搜索工具补充 LLM 的输入生成弱点
5. **断言策略增强** — 提升 Mutation Score

## 3. 架构设计：3 Agent + 2 工具模块

保持与 MACO 同构的 3 Agent 架构，创新体现在每个环节的增强：

```
目标 Java 方法
  ↓
TaskAgent（增强：AST + LLM 语义补充 + 输出结构化依赖图谱）
  ↓
依赖构造知识图谱 + LightRAG 检索依赖处理经验
  ↓
PlanAgent（增强：LightRAG 检索 + 断言策略设计）
  ↓
EvoSuite 辅助搜索输入和边界值
  ↓
GenerationAgent（增强：StaticGuard 符号校验 + 编译反馈修复）
  ↓
编译、运行、覆盖率、依赖覆盖、变异测试反馈
  ↓
继续修复和补充测试
```

### 3 Agent 对比 MACO 的增强

| Agent | MACO 做法 | 我们的增强 |
|-------|----------|----------|
| TaskAgent | AST 分析依赖 | AST + **LLM 语义补充** + **输出结构化依赖图谱** |
| PlanAgent | 生成测试计划 | 计划生成 + **LightRAG 检索相似依赖处理经验** + **断言策略设计** |
| GenerationAgent | 生成代码 | 生成代码 + **StaticGuard 符号校验** + **编译反馈修复** |

### 工具模块（不是独立 Agent）

- **StaticGuard**：符号校验模块，集成在 GenerationAgent 中
- **AssertionEnhancer**：断言增强模块，集成在 PlanAgent 中

**关键定位：** 创新点不在 Agent 数量，而在每个环节的增强机制。

## 4. DCCI 指标

为了避免直接照搬 MACO 的 MDCI，本项目提出 DCCI（Dependency Construction Complexity Index，依赖构造复杂度指标）。

DCCI 不只衡量依赖数量和调用深度，而是衡量目标方法在测试中是否难以构造、隔离、mock 和断言。

### 初步公式

```
DCCI = 0.25E + 0.20D + 0.15I + 0.15S + 0.10R + 0.10O + 0.05P
```

**含义：**
- E：外部调用数量
- D：依赖模块或依赖类数量
- I：依赖注入与构造难度
- S：状态依赖难度（静态状态、缓存、单例、全局变量）
- R：外部资源依赖难度（文件、网络、数据库、时间、随机数、环境变量）
- O：测试 oracle 或断言难度
- P：参数复杂度

### 权重确定

- 基于软件复杂度度量文献（CK metrics、McCabe、coupling metrics）设定初始权重
- 在论文中明确引用权重来源的文献依据
- 通过敏感性分析证明结论对权重选择不敏感（±30% 扰动，Spearman ≥ 0.85）

DCCI 用于筛选实验对象和进行复杂度分层分析。

## 5. 数据集来源

总规模：**100-150 个 focal methods**

| 数据源 | 数量 | 筛选标准 |
|--------|------|----------|
| MACO 原数据 | 41 个 | 全部保留，用于对齐复现 |
| Defects4J | 50-60 个 | DCCI ≥ 中位数，优先选有真实缺陷的方法 |
| SF110 | 30-50 个 | DCCI 分层抽样（Low/Medium/High 各 10-15 个） |

### 筛选流程

1. 对候选方法计算 DCCI
2. 排除 trivial 方法（DCCI < 阈值下限）
3. 按 DCCI 分层抽样，确保 Low/Medium/High 各占约 1/3
4. SF110 上只跑覆盖率指标，不跑变异测试（控制成本）

## 6. 实验设计（精简为 3 个实验）

实验结构与 MACO 对齐（3 个实验），但每个实验深度更强。

### 6.1 实验 1 (RQ1)：主对比实验

**研究问题：** 本文方法相比现有方法在测试生成质量上是否有显著提升？

**对比方法分层：**

**实际运行（主实验核心对比）：**
- EvoSuite
- 普通 RAG + LLM（明确定义：方法级 chunk、向量检索 top-5、无结构化图谱）
- 本文完整方法（Ours Full）

**小规模补充（sanity baseline）：**
- Direct LLM：只在小样本或 MACO 原 41 个方法上运行，用作裸 LLM 下界，不作为全量主 baseline。

**引用/相关工作对比：**
- MACO：使用原论文公开结果，主要用于 MACO 原 41 个方法和共同指标上的 published comparison；不完整复刻运行。
- ChatUniTest：不完整复刻，放入 Related Work 或引用原论文结果；若后续发现官方实现易复现，再作为补充实验。

**关键理由：** Direct LLM 与 RAG + LLM 都属于简单 LLM 测试生成方法，但 RAG + LLM 更能直接验证本文核心创新：普通检索不足，依赖构造知识图谱 + LightRAG + 多 Agent 增强才是主要提升来源。因此 RAG + LLM 进入全量主实验，Direct LLM 降级为小规模下界参考。

**数据集：** 全部 100-150 个方法

**评价指标体系：质量阶梯（四层递进）**

我们从四个互补维度评价生成的测试，形成质量阶梯：

| 质量层级 | 指标 | 为什么需要这个指标 | 对应的创新模块 | 消融验证 |
|---------|------|------------------|--------------|---------|
| **第1层：编译通过** | Compilation Pass Rate<br>Symbol Error Rate | 现有 LLM 方法在高依赖场景下编译通过率低，主要原因是符号幻觉（漏 import、写错类名、混淆重载）。这是验证 StaticGuard 有效性的**直接指标**。 | StaticGuard 符号校验 | A2 (w/o StaticGuard) 应在这两个指标上明显下降 |
| **第2层：运行通过** | Test Pass Rate | 编译通过不代表能运行。高依赖方法的测试常因 mock 配置错误、依赖构造失败而运行时报错。衡量测试在**真实执行环境**下的可用性。 | 知识图谱 + LightRAG（mock 经验检索） | A1 (w/o 知识图谱+LightRAG) 应导致 mock 配置错误增多，Test Pass Rate 下降 |
| **第3层：覆盖率** | Line Coverage<br>Branch Coverage | 最基本的测试充分性指标，也是与已有工作（MACO、ChatUniTest、EvoSuite）对比的**通用基准**，确保实验可比性。覆盖率是必要条件，不是充分条件。 | EvoSuite 混合 + 反馈循环 | A3 (w/o EvoSuite) 和 A5 (w/o 反馈) 应在覆盖率上下降 |
| **第4层：有效性** | Mutation Score<br>Assertion Quality | 高覆盖率不等于高质量测试。一个只写 `assertNotNull` 的测试可以覆盖很多代码，但发现不了 bug。Mutation Score 衡量测试是否真的能检测代码变异（即潜在缺陷），Assertion Quality 衡量断言是否具体、有意义。回答测试的**真正价值**。 | 断言策略增强 | A4 (w/o 断言增强) 应导致 Mutation Score 下降 |

**关键逻辑：** 这个多层次评价体系解决了现有工作的一个关键局限——仅报告覆盖率指标，无法区分有意义的测试和 trivially passing 的测试。每一层对应高依赖方法测试生成中的一个具体挑战，我们的方法通过不同的增强模块在所有四层都有提升。

**统计分析：**
- 对实际运行方法（EvoSuite、RAG + LLM、Ours Full）报告平均值、中位数、标准差、箱线图、Wilcoxon signed-rank test、Cliff's Delta。
- 对 MACO/ChatUniTest 的原论文结果只做 published-result comparison；如果没有 per-method 数据，不做 paired Wilcoxon，避免统计口径不严谨。

**变异测试范围：** 仅在 MACO 原数据 + Defects4J 上计算 Mutation Score（SF110 不跑，控制成本）

### 6.2 实验 2 (RQ2)：消融实验

**研究问题：** 各增强模块分别贡献了多少？

**消融变体（5 个）：**

| 编号 | 消融变体 | 验证目标 |
|------|----------|----------|
| A1 | w/o 依赖构造知识图谱 + LightRAG | 去掉整个图谱检索模块 |
| A2 | w/o StaticGuard 符号校验 | 验证是否降低编译通过率和符号正确率 |
| A3 | w/o EvoSuite 输入搜索 | 验证 LLM 独立生成输入的能力 |
| A4 | w/o 断言增强 | 验证对 Mutation Score 的影响 |
| A5 | w/o 覆盖率反馈循环 | 验证单轮生成 vs 迭代修复的差距 |

**说明：**
- 原"w/o 依赖构造知识图谱"和"w/o LightRAG"合并为 A1，因为图谱是 LightRAG 的数据源
- 原"w/o 传统测试设计技术"去掉，因为难以独立隔离且与 PlanAgent 强耦合

**数据集：** Defects4J + MACO 原数据（约 90-100 个方法）

**指标：** 同实验 1

**EvoSuite 双重身份处理：** 消融 A3 的结果直接回答公平性问题——额外报告"本文方法（不含 EvoSuite）vs 纯 EvoSuite"，证明即使不用 EvoSuite 辅助仍有优势。论文讨论中说明这是"互补"而非"替代"关系。

### 6.3 实验 3 (RQ3)：DCCI 分析实验

**研究问题：** DCCI 是否有效？方法在高 DCCI 场景下优势是否更明显？

包含三个子部分：

#### 6.3.1 权重确定与敏感性分析
- 基于软件复杂度度量文献（CK metrics、McCabe、coupling metrics）设定初始权重
- 在论文中明确引用权重来源的文献依据
- 对每个权重在 ±30% 范围内扰动（其余等比例调整使总和为 1）
- 报告扰动后方法排序的 Spearman 相关系数（目标 ≥ 0.85）
- 证明结论对权重选择不敏感

#### 6.3.2 DCCI vs MDCI 对比
- 在 MACO 原 41 个方法上同时计算 DCCI 和 MDCI
- 对比两个指标与实际测试生成难度（编译通过率、覆盖率）的相关性
- 用 Spearman rank correlation 报告

#### 6.3.3 DCCI 分层分析
- 按 Low DCCI、Medium DCCI、High DCCI 分层
- 验证方法在高 DCCI 场景下优势是否更明显
- 数据集：全部方法

**变异工具：** PIT（Java 主流变异测试工具）

### 总实验运行次数估算

核心运行对象调整为 **3 actual-run methods/baselines + Ours ablations + published comparison**：

- RQ1 主实验：3 个实际运行对象 × 100-150 个方法 ≈ **300-450 次运行**
- Direct LLM sanity baseline：20-41 个方法 ≈ **20-41 次运行**
- RQ2 消融实验：5 个消融变体 × 90-100 个方法 ≈ **450-500 次运行**
- MACO/ChatUniTest：引用原论文结果，不计入复刻运行成本

预计总运行量约 **770-991 次**。第一阶段优先交付 RQ1 首轮结果，若全量方法列表或外部工具未完全就绪，则先完成 MACO + Defects4J 核心子集，并把 SF110 标注为补充运行中。

## 7. 论文结构建议

**Title:** Dependency-Aware Test Generation for Complex Java Methods via Knowledge Graph and Multi-Agent Collaboration

**Abstract 核心信息：**
- 问题：高依赖复杂 Java 方法测试生成困难
- 方法：依赖构造知识图谱 + LightRAG + 增强型多智能体
- 创新：DCCI 指标 + 知识图谱 + 符号约束 + 混合搜索
- 结果：在 100-150 个方法上优于 MACO 和其他 baseline

**Section 结构：**
1. Introduction
2. Background & Related Work
3. Approach
   - 3.1 Overview（3 Agent 架构图）
   - 3.2 Dependency Construction Knowledge Graph
   - 3.3 Enhanced TaskAgent
   - 3.4 Enhanced PlanAgent with LightRAG
   - 3.5 Enhanced GenerationAgent with StaticGuard
   - 3.6 DCCI Metric
4. Evaluation
   - 4.1 RQ1: Main Comparison
   - 4.2 RQ2: Ablation Study
   - 4.3 RQ3: DCCI Analysis
5. Discussion
6. Threats to Validity
7. Conclusion

## 8. 评价指标的自圆其说策略

### 在 Evaluation 部分开头加一段

> **Evaluation Metrics.** We evaluate the generated tests from four complementary dimensions, forming a quality hierarchy:
> 
> 1. **Compilability** — whether the generated test can compile without errors (Compilation Pass Rate, Symbol Error Rate);
> 2. **Runnability** — whether the test executes successfully (Test Pass Rate);
> 3. **Coverage** — how much of the target method is exercised (Line Coverage, Branch Coverage);
> 4. **Effectiveness** — whether the test can actually detect faults (Mutation Score, Assertion Quality).
> 
> This multi-level evaluation addresses a key limitation of prior work that primarily reports coverage metrics, which alone cannot distinguish between meaningful tests and trivially passing ones. Each level corresponds to a specific challenge in test generation for high-dependency methods, and our approach targets improvements at all four levels through different enhancement modules.

### 在结果表格中按层级分组

```
Table X: Main Comparison Results (RQ1)

Method              | Compilability      | Runnability | Coverage        | Effectiveness
                    | Comp% | SymErr%  | Pass%       | Line% | Branch% | Mutation% | AssertQ
--------------------|-------|----------|-------------|-------|---------|-----------|--------
EvoSuite            | ...   | ...      | ...         | ...   | ...     | ...       | ...
RAG + LLM           | ...   | ...      | ...         | ...   | ...     | ...       | ...
Ours (Full)         | ...   | ...      | ...         | ...   | ...     | ...       | ...
Direct LLM (sanity) | ...   | ...      | ...         | ...   | ...     | ...       | ...
MACO (published)    | ...   | ...      | ...         | ...   | ...     | paper-only| paper-only
ChatUniTest (pub.)  | ...   | ...      | ...         | ...   | ...     | paper-only| paper-only
```

### 在 Discussion 中强化这个逻辑

> Our evaluation framework reveals that test generation quality is not a single-dimensional problem. A method may achieve high coverage but fail at earlier stages (compilation, execution) or later stages (fault detection). For instance, Direct LLM achieves X% coverage but only Y% compilation rate, indicating that raw LLM output suffers from symbol hallucination. In contrast, our StaticGuard module raises compilation rate to Z%, demonstrating the value of symbol-level constraints.

## 9. 后续实现优先级

### 已完成（原型）
- ✅ 3 Agent 基础实现（TaskAgent, PlanAgent, GenerationAgent）
- ✅ LLM 调用层（OpenAI 兼容格式）
- ✅ Java AST 解析（javalang）
- ✅ 编译反馈模块
- ✅ Pipeline 端到端串联

### 待实现（按优先级）
1. **DCCI 计算模块** — 用于数据集筛选，优先级最高
2. **依赖构造知识图谱** — 核心创新，需要设计图谱 schema
3. **LightRAG 检索层** — 集成到 PlanAgent
4. **StaticGuard 符号校验** — 集成到 GenerationAgent
5. **EvoSuite 集成** — 输入搜索辅助
6. **Baseline 实现** — 优先实现 EvoSuite、RAG+LLM、Ours Full 的统一运行与统计；Direct LLM 只做小规模 sanity baseline；MACO/ChatUniTest 先做 published comparison
7. **评价指标计算** — 覆盖率、变异测试、断言质量评估

## 10. 关键风险与应对

| 风险 | 应对策略 |
|------|---------|
| 知识图谱构建成本高 | 先用小规模图谱验证可行性，再扩展 |
| LightRAG 检索效果不理想 | 准备 fallback：普通向量检索 + 结构化查询 |
| DCCI 权重难以确定 | 敏感性分析证明稳健性，权重变化不影响结论 |
| 实验规模大（约 770-991 次运行） | 优先跑 RQ1 核心实际运行对象（EvoSuite、RAG+LLM、Ours Full），Direct LLM 只做小规模 sanity baseline，SF110 作为补充 |
| Mutation Score 计算成本高 | 只在 MACO + Defects4J 上跑，SF110 跳过 |

## 12. 第一阶段目标计划（截至 2026-06-09）

**目标：** 面向导师展示本文评价指标、评审流程和 RQ1 首轮实验结果。第一阶段交付的是可解释的首轮实验闭环，不等同于最终论文定稿实验。

### 12.1 交付物

1. **研究计划更新**：明确 baseline 分层，删除“6 baselines 全量运行”的实验口径。
2. **评价指标与评审流程表**：把四层质量阶梯和 8 个质量门落到系统评审流程。
3. **导师展示材料**：6 页左右，讲清楚研究问题、自动评审闭环、质量阶梯、8 个质量门、实验设计和首轮结果。
4. **RQ1 首轮实验结果**：优先跑 EvoSuite、RAG + LLM、Ours Full；Direct LLM 只跑小规模 sanity set；MACO/ChatUniTest 使用 published comparison。

### 12.2 8 个质量门

| 质量门 | 检查内容 | 不合格处理 |
|--------|----------|------------|
| 合规性评审 | 语法、import、类名、方法名、依赖符号 | 进入修复；多轮修不好丢弃 |
| 可执行性评审 | Maven/JUnit 编译与运行 | 记录失败原因并反馈修复 |
| 有效性评审 | 断言、异常路径、状态变化、依赖交互 | 弱断言标记为低质量 |
| 覆盖贡献评审 | JaCoCo 行/分支覆盖增益 | 无覆盖增益且不能杀死变异体则低价值 |
| 冗余性评审 | 路径、输入、断言重复度 | 重复测试压缩或删除 |
| 代表性/风险评审 | 高 DCCI、边界、异常、外部依赖路径 | 高风险路径优先保留 |
| 反馈修复机制 | 编译、运行、覆盖、断言问题日志 | 反馈给 Agent 继续修复 |
| 最终保留规则 | 能编译、能运行、有覆盖贡献、有具体断言、低冗余、代表高风险路径 | 进入最终测试集 |

### 12.3 时间安排

| 日期 | 目标 |
|------|------|
| 06-03 到 06-04 | 修改研究计划和 Excel；固定 RQ1 方法列表和运行配置 |
| 06-05 到 06-06 | 跑 EvoSuite、RAG + LLM、Ours Full 的首轮实验；同步记录失败原因 |
| 06-07 | 补跑失败项；整理 Direct LLM 小样本结果 |
| 06-08 | 生成导师展示图表、流程图和 3-5 条初步结论 |
| 06-09 | 最终检查展示材料、Excel、实验结果表，准备汇报口径 |

## 11. 研究定位总结

本项目不是简单给 MACO 打补丁，而是提出一种面向高依赖复杂 Java 方法的测试生成增强框架。保持 3 Agent 架构与 MACO 同构，创新体现在每个环节的增强机制。

**核心贡献：**
1. 依赖构造知识图谱 + LightRAG 图谱增强检索（最大创新）
2. DCCI 依赖构造复杂度指标（方法学贡献）
3. StaticGuard 符号约束，降低 LLM 幻觉
4. LLM + EvoSuite 混合输入搜索
5. 断言策略增强，提升测试有效性

**论文主线：** 依赖构造知识图谱 + LightRAG + 增强型 3 Agent 多智能体测试生成
