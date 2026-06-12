# 研究计划：高依赖复杂 Java 单元测试生成增强方案

## 1. 研究定位

本项目以 MACO 论文为重要参考，但不做 MACO 的完整复刻。本文的核心目标是面向高依赖复杂 Java 方法，构建一套更可执行、更可评估的单元测试生成增强框架。

当前研究主线调整为：

```text
依赖分析
  -> 依赖构造知识图谱 / LightRAG 检索
  -> 测试计划生成
  -> StaticGuard 符号约束
  -> 测试代码生成
  -> 编译 / 运行反馈修复
  -> 覆盖率与复杂度分析
```

本文不追求完整复现 MACO、ChatUniTest 或 SF110 全量 benchmark，而是优先形成可交付、可解释、可运行的实验闭环。

## 2. 核心贡献

### 2.1 保留为当前论文核心贡献

1. **依赖构造知识图谱 + LightRAG 检索**
   - 存储和检索依赖如何构造、mock、隔离和处理失败。
   - 重点解决高依赖方法中依赖语义和构造经验缺失的问题。

2. **DCCI 指标**
   - DCCI（Dependency Construction Complexity Index）用于衡量依赖构造复杂度。
   - 相比 MACO 的 MDCI，DCCI 更关注依赖是否难以构造、mock、隔离和断言。

3. **StaticGuard 符号约束**
   - 降低 LLM 生成测试时的符号幻觉。
   - 重点减少漏 import、类名错误、方法签名错误和 JUnit/Mockito 使用错误。

4. **编译 / 运行反馈修复机制**
   - 将编译错误和运行错误反馈给生成流程。
   - 支持多轮修复，提高生成测试的可用性。

5. **增强型 3-Agent 框架**
   - 保持与 MACO 同构的 TaskAgent、PlanAgent、GenerationAgent 思路。
   - 创新点不在 Agent 数量，而在依赖检索、符号约束、反馈修复和复杂度评估。

### 2.2 降级或后置的内容

以下内容不再作为当前论文核心贡献：

| 内容 | 调整 |
|---|---|
| LLM + EvoSuite 混合输入搜索 | EvoSuite 降级为 baseline，不作为 Ours Full 内部模块 |
| 断言策略增强 | 放入 Future Work 或补充实验 |
| Mutation Score 全量评估 | 放入补充实验或后续扩展 |
| SF110 大规模扩展实验 | 放入 Future Work |
| ChatUniTest 完整复现 | 仅作为 Related Work / published-reference comparison |

## 3. 方法架构

调整后的方法架构如下：

```text
目标 Java 方法
  ↓
TaskAgent：AST 分析 + LLM 语义补充 + 依赖识别
  ↓
依赖构造知识图谱 / LightRAG：检索相似依赖处理经验
  ↓
PlanAgent：生成测试计划和依赖处理方案
  ↓
GenerationAgent：生成 JUnit 测试代码
  ↓
StaticGuard：符号、import、类名、方法签名校验
  ↓
编译 / 运行反馈修复
  ↓
覆盖率、运行结果、复杂度分析
```

EvoSuite 不再作为 Ours Full 的内部模块，而是作为传统自动测试生成 baseline。

## 4. DCCI 指标

为了避免直接照搬 MACO 的 MDCI，本项目提出 DCCI（Dependency Construction Complexity Index，依赖构造复杂度指标）。

初步公式：

```text
DCCI = 0.25E + 0.20D + 0.15I + 0.15S + 0.10R + 0.10O + 0.05P
```

含义：

| 符号 | 含义 |
|---|---|
| E | 外部调用数量 |
| D | 依赖模块或依赖类数量 |
| I | 依赖注入与构造难度 |
| S | 状态依赖难度，如静态状态、缓存、单例、全局变量 |
| R | 外部资源依赖难度，如文件、网络、数据库、时间、随机数、环境变量 |
| O | 测试 oracle 或断言难度 |
| P | 参数复杂度 |

DCCI 的用途：

1. 从 Defects4J 中筛选高依赖复杂方法。
2. 对实验对象做 Low / Medium / High 复杂度分层。
3. 与 MACO 的 MDCI 做相关性对比。
4. 分析方法在高 DCCI 场景下是否更有优势。

## 5. 数据集设计

### 5.1 当前保留的数据集

| 数据集 | 定位 | 筛选方式 | 用途 |
|---|---|---|---|
| Defects4J | 主实验数据集 | 使用 DCCI 筛选高依赖复杂方法 | 证明本文方法在真实项目上的有效性 |
| MACO original 41 / MACO-aligned 41 | 对齐实验数据集 | 使用 MACO 的 MDCI 规则或作者提供清单 | 增强与 MACO 原论文的可比性 |

### 5.2 删除或后置的数据集

| 数据集 | 调整 |
|---|---|
| SF110 | 从当前实验删除，放入 Future Work |

删除 SF110 的原因：

- 项目数量多，构建和依赖环境复杂。
- 当前阶段会显著增加实验成本。
- 对第一阶段证明方法有效性的边际收益不高。

## 6. MACO 对齐实验设计

MACO 数据不作为主实验，而作为对齐实验。

### 6.1 如果作者提供原始 41 方法

建立：

```text
maco_original_41.json
```

使用作者提供的：

- 41 focal methods 清单
- 项目版本 / commit
- 类名、方法名、方法签名
- MDCI 分数或筛选元数据（如有）

论文表述：

```text
We evaluate our method on the original MACO focal-method dataset provided by the authors.
```

### 6.2 如果作者不提供原始数据

构建：

```text
maco_aligned_41.json
```

依据 MACO 论文公开规则重建：

```text
MDCI = 0.3E + 0.3D + 0.1C + 0.05P + 0.15T + 0.1CT
MDCI >= 1.0
```

目标项目：

| 项目 | 版本 / commit | Java | 目标方法数 |
|---|---|---:|---:|
| Commons-CLI | 1.5.0 | 8 | 6 |
| Commons-CSV | 1.10.0 | 8 | 5 |
| Commons-codec | 3a6873e | 8 | 5 |
| Commons-collections4 | 4.5.0 | 8 | 14 |
| JDom2 | 2.0.6 | 17 | 9 |
| Windward | 1.5.1 | 8 | 2 |

论文表述：

```text
We reconstruct a MACO-aligned subset following the MDCI-based selection protocol described in MACO.
```

### 6.3 MACO 对齐实验的限制

如果没有 MACO 原始方法清单和完整实现，不做以下声明：

```text
Our method strictly outperforms MACO.
```

更稳妥的声明是：

```text
MACO results are used as published-reference comparison, while our executable comparisons are conducted against reproducible baselines.
```

## 7. 实验设计

### 7.1 RQ1：主实验

**研究问题：** 本文方法相比可复现 baseline 是否有效？

数据集：

- Defects4J

对比方法：

| 方法 | 定位 |
|---|---|
| EvoSuite | 传统自动测试生成 baseline |
| RAG + LLM | 大模型检索增强 baseline |
| Ours Full | 本文完整方法 |

核心指标：

- Compilation Pass Rate
- Test Pass Rate
- Line Coverage
- Branch Coverage

### 7.2 RQ2：核心消融实验

**研究问题：** 核心增强模块分别贡献了多少？

数据集：

- Defects4J 子集

消融版本：

| 编号 | 消融版本 | 验证目标 |
|---|---|---|
| A1 | w/o Knowledge Graph / LightRAG | 验证依赖经验检索的作用 |
| A2 | w/o StaticGuard | 验证符号约束对编译率和符号错误率的影响 |
| A3 | w/o Feedback Repair | 验证编译 / 运行反馈修复机制的作用 |

删除的消融：

| 原消融 | 删除原因 |
|---|---|
| w/o EvoSuite | EvoSuite 不再作为 Ours Full 内部模块 |
| w/o AssertionEnhancer | 断言增强不作为当前核心贡献 |

### 7.3 RQ3：DCCI 分析实验

**研究问题：** DCCI 是否比 MDCI 更能解释测试生成难度？

数据集：

- Defects4J
- MACO original 41 或 MACO-aligned 41

分析内容：

1. 对同一批方法同时计算 DCCI 和 MDCI。
2. 比较 DCCI / MDCI 与编译率、运行率、覆盖率的相关性。
3. 按 Low / Medium / High DCCI 分层，观察本文方法在高复杂度方法上的表现。

### 7.4 RQ4：MACO 对齐实验

**研究问题：** 本文方法在 MACO 风格数据上是否仍然有效？

数据集：

- MACO original 41，若作者提供。
- MACO-aligned 41，若作者未提供。

对比方法：

- EvoSuite
- RAG + LLM
- Ours Full

指标：

- Compilation Pass Rate
- Test Pass Rate
- Line Coverage
- Branch Coverage

## 8. 评价指标

### 8.1 核心指标

| 指标 | 用途 |
|---|---|
| Compilation Pass Rate | 判断生成测试是否能编译 |
| Test Pass Rate | 判断生成测试是否能真实运行 |
| Line Coverage | 判断测试覆盖能力 |
| Branch Coverage | 判断分支覆盖能力 |

### 8.2 补充指标

| 指标 | 用途 |
|---|---|
| Symbol Error Rate | 分析 StaticGuard 是否降低符号错误 |
| DCCI / MDCI correlation | 支撑 DCCI 指标有效性 |
| Mutation Score | 后置或小样本补充 |
| Assertion Quality | 后置或小样本补充 |

## 9. Baseline 处理

### 9.1 当前正式运行 baseline

| Baseline | 是否运行 | 说明 |
|---|---|---|
| EvoSuite | 是 | 传统自动测试生成工具 |
| RAG + LLM | 是 | 检索增强大模型 baseline |
| Direct LLM | 可选小样本 | sanity baseline，不进入主实验 |

### 9.2 不完整复现的已有方法

| 方法 | 处理方式 |
|---|---|
| MACO | 使用 published-reference comparison，不完整复现 |
| ChatUniTest | 放入 Related Work，不作为可运行 baseline |

## 10. 实施优先级

| 优先级 | 任务 |
|---|---|
| P0 | 固定 Defects4J 主实验方法集 |
| P0 | 跑通 EvoSuite、RAG + LLM、Ours Full 的统一实验入口 |
| P1 | 实现测试运行通过率统计 |
| P1 | 接入行覆盖率和分支覆盖率统计 |
| P1 | 完成 A1 / A2 / A3 核心消融 |
| P2 | 联系 MACO 作者获取原始 41 方法 |
| P2 | 构建 MACO-aligned fallback |
| P3 | 完成 DCCI vs MDCI 分析 |
| P4 | 小样本补充 Mutation Score / Assertion Quality |
| P5 | 将 SF110 扩展放入 Future Work |

## 11. 风险与应对

| 风险 | 应对 |
|---|---|
| MACO 作者不回复 | 使用 MACO-aligned fallback |
| MACO-aligned 与原始 41 方法不完全一致 | 明确说明不是 exact reproduction |
| Defects4J 方法构建失败 | 保留 buildability check，只使用可构建方法 |
| DCCI 权重被质疑 | 做敏感性分析或相关性分析 |
| Mutation Score 成本高 | 不作为主实验指标 |
| 实验范围再次膨胀 | 坚持主实验 + 精简消融 + MACO 对齐三条线 |

## 12. 论文主线总结

本文最终定位为：

```text
一种面向高依赖复杂 Java 方法的增强型单元测试生成框架。
```

实验主线为：

```text
Defects4J 主实验
  + 核心模块消融
  + DCCI vs MDCI 分析
  + MACO original/aligned 对齐实验
```

一句话总结：

```text
本项目不完整复刻 MACO，而是在 MACO 启发下提出更聚焦依赖构造复杂度的测试生成增强方案；MACO 41 方法只作为对齐桥梁，Defects4J 和 DCCI 才是当前主实验主线。
```
