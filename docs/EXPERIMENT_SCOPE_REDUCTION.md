# 实验范围删减与 MACO 对齐实验说明

## 1. 背景

原实验设计同时包含多个数据集、多个 baseline、多个消融模块和多个评价指标，整体工作量过大。

主要问题包括：

| 维度 | 原设计 | 风险 |
|---|---|---|
| 数据集 | MACO 41、Defects4J、SF110 | 环境和筛选成本高 |
| baseline | EvoSuite、RAG + LLM、Direct LLM、MACO、ChatUniTest | 运行和解释成本高 |
| 消融 | w/o KG/LightRAG、w/o StaticGuard、w/o Feedback、w/o EvoSuite、w/o AssertionEnhancer | 实验组合过多 |
| 指标 | 编译率、运行率、覆盖率、Mutation Score、断言质量、DCCI/MDCI | 主线容易分散 |
| 复现 | 试图复刻 MACO 原论文数据 | 原始 41 方法未公开，精确复现不确定 |

因此当前方案调整为：

```text
主实验做深
消融实验做精
MACO 只做对齐
SF110 和复杂补充指标后置
```

## 2. 删除 ChatUniTest 实验

### 调整

ChatUniTest 不再作为本文正式运行的 baseline。

### 理由

- 完整复现成本较高。
- 与本文最直接的对比关系弱于 EvoSuite 和 RAG + LLM。
- MACO 原论文已经将 ChatUniTest 作为对比方法讨论过。
- 若强行复现，容易把工作量转移到别人方法的工程适配上。

### 论文处理

ChatUniTest 只放入 Related Work 或 published-reference comparison。

推荐表述：

```text
ChatUniTest is discussed as related work. Since its official reproduction requires additional engineering effort and is not the primary focus of this study, we do not include it as an executable baseline.
```

## 3. 删除 SF110 当前实验

### 调整

SF110 从当前实验中删除，放入 Future Work。

### 理由

- SF110 项目数量多，构建环境复杂。
- Java 版本、Maven 依赖和测试框架差异可能引入大量额外问题。
- 当前阶段更需要稳定完成 Defects4J 主实验和 MACO 对齐实验。
- SF110 对第一阶段证明方法有效性的边际收益不高。

### 论文处理

推荐表述：

```text
Extending the evaluation to larger benchmark suites such as SF110 is left as future work.
```

## 4. 删除 w/o EvoSuite 消融

### 调整

删除 `w/o EvoSuite` 消融实验。

### 前提

EvoSuite 不再作为 Ours Full 的内部模块，而是作为传统自动测试生成 baseline。

### 理由

如果 EvoSuite 只是 baseline，就不存在从 Ours Full 中移除 EvoSuite 的消融必要。

调整后：

```text
EvoSuite = baseline
Ours Full = 不包含 EvoSuite 的本文方法
```

推荐表述：

```text
EvoSuite is used as a traditional search-based test generation baseline, rather than as an internal component of our full approach.
```

## 5. 删除 w/o AssertionEnhancer 消融

### 调整

删除 `w/o AssertionEnhancer` 消融实验。

### 理由

- 断言增强需要 Mutation Score 或 Assertion Quality 支撑。
- 这会引入额外指标和实验成本。
- 当前论文主线优先证明编译、运行和覆盖率层面的有效性。

### 论文处理

断言增强不作为当前核心贡献，放入 Future Work 或补充实验。

推荐表述：

```text
Assertion enhancement and mutation-oriented test improvement are left as future extensions.
```

## 6. MACO 对齐实验处理

MACO 不作为主实验数据，而作为对齐实验。

### 6.1 作者提供原始数据时

如果 MACO 作者提供 41 个 focal methods，则建立：

```text
maco_original_41.json
```

并在该数据集上运行：

- EvoSuite
- RAG + LLM
- Ours Full

推荐表述：

```text
We evaluate our method on the original MACO focal-method dataset provided by the authors.
```

### 6.2 作者不提供原始数据时

如果作者不提供原始数据，则构建：

```text
maco_aligned_41.json
```

按照 MACO 论文公开规则重建：

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

推荐表述：

```text
We reconstruct a MACO-aligned subset following the MDCI-based selection protocol described in MACO.
```

### 6.3 限制说明

如果没有 MACO 原始方法清单和完整实现，不做严格击败 MACO 的声明。

不推荐表述：

```text
Our method strictly outperforms MACO.
```

推荐表述：

```text
MACO results are used as published-reference comparison, while our executable comparisons are conducted against reproducible baselines.
```

## 7. 最终保留内容

### 7.1 数据集

| 数据集 | 状态 | 用途 |
|---|---|---|
| Defects4J | 保留 | 主实验 |
| MACO original 41 / MACO-aligned 41 | 保留 | 对齐实验 |
| SF110 | 删除当前实验 | Future Work |

### 7.2 Baseline

| 方法 | 状态 | 用途 |
|---|---|---|
| EvoSuite | 保留 | 传统自动测试生成 baseline |
| RAG + LLM | 保留 | LLM 检索增强 baseline |
| Ours Full | 保留 | 本文方法 |
| Direct LLM | 可选小样本 | sanity baseline |
| ChatUniTest | 删除运行实验 | Related Work |
| MACO | 不完整复现 | published-reference comparison |

### 7.3 消融实验

| 编号 | 消融 | 状态 |
|---|---|---|
| A1 | w/o Knowledge Graph / LightRAG | 保留 |
| A2 | w/o StaticGuard | 保留 |
| A3 | w/o Feedback Repair | 保留 |
| A4 | w/o EvoSuite | 删除 |
| A5 | w/o AssertionEnhancer | 删除 |

### 7.4 指标

核心指标：

- Compilation Pass Rate
- Test Pass Rate
- Line Coverage
- Branch Coverage

补充指标：

- Symbol Error Rate
- DCCI / MDCI correlation
- Mutation Score（后置或小样本）
- Assertion Quality（后置或小样本）

## 8. 最终实验结构

| RQ | 数据集 | 方法 | 指标 | 作用 |
|---|---|---|---|---|
| RQ1 | Defects4J | EvoSuite、RAG + LLM、Ours Full | 编译率、运行率、行覆盖率、分支覆盖率 | 证明方法有效 |
| RQ2 | Defects4J 子集 | Ours Full、A1、A2、A3 | 编译率、运行率、覆盖率、符号错误率 | 证明模块贡献 |
| RQ3 | Defects4J + MACO original/aligned | DCCI、MDCI | 相关性、复杂度分层 | 证明 DCCI 价值 |
| RQ4 | MACO original/aligned 41 | EvoSuite、RAG + LLM、Ours Full | 编译率、运行率、覆盖率 | 增强与 MACO 可比性 |

## 9. 执行优先级

| 优先级 | 任务 |
|---|---|
| P0 | 固定 Defects4J 主实验方法集 |
| P0 | 跑通 EvoSuite、RAG + LLM、Ours Full |
| P1 | 实现测试运行通过率统计 |
| P1 | 实现行覆盖率和分支覆盖率统计 |
| P1 | 完成 A1 / A2 / A3 消融 |
| P2 | 联系 MACO 作者获取原始 41 方法 |
| P2 | 构建 MACO-aligned fallback |
| P3 | 完成 DCCI vs MDCI 分析 |
| P4 | 小样本补充 Mutation Score / Assertion Quality |
| P5 | 将 SF110 放入 Future Work |

## 10. 总结

删减后的实验主线为：

```text
Defects4J 主实验
  + 核心模块消融
  + DCCI vs MDCI 分析
  + MACO original/aligned 对齐实验
```

最终定位：

```text
本文不完整复刻 MACO，而是在 MACO 启发下提出更聚焦依赖构造复杂度的测试生成增强方案。
```

MACO 41 方法只作为对齐桥梁，Defects4J 和 DCCI 才是当前主实验主线。
