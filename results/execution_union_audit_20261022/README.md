# 覆盖率精确合并与正式运行前离线审计（2026-10-22）

本批仅重算已有数据和运行离线回归测试：0 次 API 调用，不是新增生成实验，也不是正式 RQ1/RQ2。历史结果和六目标原报告均保留。

## 已完成：原始执行数据精确合并

`scripts/merge_kcf_execution_coverage.py` 按当前明确认可的 5 套通过测试定位原始 XML、exec 和 JUnit 日志。要求 XML 哈希一致、原始执行来源唯一、正数测试全部通过、必要语义复核已经完成；冻结每个输入的哈希。校验六项目编译类树与固定参考一致、JaCoCo CLI 哈希一致；发现不同执行类 ID 或报告不匹配即报错。

每项目先 `jacococli execinfo` 检查，再 `merge` 原始探针数据，最后仅对固定 main classes 生成一个报告。没有通过测试的项目生成零覆盖报告，六目标分母不缩小。不会纳入 Codec/Windward 失败套件或未认可修复。

| 六目标口径 | 行 | 分支 |
|---|---|---|
| 之前 XML 最大值汇总 | 57/136（41.9%） | 29/90（32.2%） |
| 本批原始 exec 精确并集 | 57/136（41.9%） | 29/90（32.2%） |

这次实际数值不变，不代表两种算法等价。真实 Java 回归案例分别执行三元条件的 true/false：两份单独报告各覆盖 1/2 分支，XML 最大值仍是 1/2，exec 合并得到 2/2。云端 Java 8 / JaCoCo 0.8.12 的 4 项专项测试全部通过；本地完整测试发现 151 项，其中 150 项通过、1 项因未指定真实 Java 工具路径而跳过，该项已在云端实际通过。

新产物：`feedback_exact_exec_union_20261022.tgz`，SHA-256 `818da710950cc232c61f27b9e97366d99f76767ae27337f60c8b172cd9b44524`。归档含逐项目合并后 exec/XML、execinfo/merge/report 日志、固定分母逐方法报告、输入来源及哈希清单、4 项专项测试日志、零调用成本记录。原始输入 exec 仍在此前已备份的 initial/seed repair/one-round 归档中。本归档经实际配置密钥扫描后导出，不含私有配置。

## 已核查：基线与消融边界

- RAG 初始生成独立于 KCF Pipeline，单次源码检索后调用 LLM，不使用 Task/Plan agents、StaticGuard 或反馈修复；获得同一冻结目标 owner/signature/source SHA。其生成成功状态只表示有代码，不等于编译或 JUnit 通过。
- A1 初始 YAML 关闭知识检索；seed repair 还需 `--disable-failure-repair-retrieval`；feedback 必须同时传 `--disable-coverage-gap-retrieval --disable-failure-repair-retrieval`。
- A2 初始和 seed repair 与 Full 同配置；仅 feedback 传 `--disable-coverage-gap-retrieval`。
- A3 初始 YAML 关闭 StaticGuard；seed repair 和 feedback 都传 `--disable-static-guard`，同时省去新增依赖声明上下文。完整性/通过性评估门槛对所有组相同，不属于被消融的生成约束。
- 反馈阶段检索与约束开关由 CLI 决定，不能假定 YAML 自动传播。现有 mock 测试覆盖反馈检索/约束分支；新模型上的完整 A1/A2/A3 对照尚未运行，不能称消融已在本版完成。

## 正式运行前仍要解决的工程项

1. 当前 feedback 内部轮间统计仍使用历史 XML 最大值逻辑；本批新增工具是精确后处理，尚未接入每轮缺口选择。必须统一轮间统计，避免后续漏算互补分支而多生成测试。本轮后处理分数一致，并不自动消除此风险。
2. RAG/EvoSuite 旧 coverage runner 允许复用输出目录，agent 未显式 `append=false`；重跑可能混入旧 exec/classes。正式启动器需拒绝复用目录并隔离每次执行；通过日志应要求实际正数 JUnit 测试，失败 XML 不计主指标。
3. 两个旧 baseline coverage runner 将 `discover_classpath_entries` 的全部目录传给 JaCoCo，包括可能存在的 test-classes；应改为共同冻结的 main classes 报告口径。JDom 的 Ant 依赖 lib/*.jar 也需与已验证 KCF classpath 对齐。
4. EvoSuite 仍以目标类为搜索单位，须明确同类多个 focal method 的共享成本；嵌套类目标和 41 方法映射需小样本验证。独立 RAG 保持其方法定义，不能为追分混入 KCF 修复。
5. 相同模型/单次 max_tokens 不等于相同总预算。正式比较前还需冻结各组总调用/预算限制、停止规则和重复运行配置，并报告实际成本。此前六目标工程测试不是公平预算的正式对照。

下一批优先完成 1–3 的实现与离线测试，再验证强制开关和小样本基线。不能直接沿用旧命令批量启动 41 方法付费对照。本文不改变 RQ1/RQ2，也不把工程修复写成新增知识适用性机制或论文创新性证据。
