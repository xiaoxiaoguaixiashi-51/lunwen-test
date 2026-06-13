# 项目当前状态归档

## 基本信息

- 本地外层目录：`D:\lunwen test`
- 本地内层实际推送仓库：`D:\lunwen test\lunwen-test`
- AutoDL 服务器目录：`/root/lunwen-test`
- Defects4J 工作目录：`/root/defects4j-work`
- GitHub 仓库：`https://github.com/xiaoxiaoguaixiashi-51/lunwen-test.git`
- 当前本地 `main` 最新已知提交：`d94a8cf Use absolute Defects4J coverage instrument path`

## 2026-06-13 当前推进状态

- 已在 AutoDL 无卡模式继续实验，项目与 Defects4J 数据保留。
- 已修复 coverage runner 的 instrument file 路径问题：
  - 原问题：`defects4j coverage` 在 `/root/defects4j-work/Lang-1b` 下执行，找不到相对路径 `experiments/.../instrument_classes.txt`。
  - 修复提交：`d94a8cf Use absolute Defects4J coverage instrument path`。
- 已完成两类生成测试的自动化 coverage 复现：
  - `LocaleUtils.toLocale`：`coverage_check_auto_v4`，25/25 coverage commands success，max line coverage 21.4%，max condition coverage 20.8%。
  - `DateUtils.isSameLocalTime`：`coverage_check_auto_dateutils_v1`，8/8 coverage commands success，max line coverage 3.1%，max condition coverage 4.5%。
- 已完成第三类生成测试的自动化 coverage：
  - `StringUtils.getLevenshteinDistance`：`coverage_check_auto_levenshtein_v1`，13/13 coverage commands success，max line coverage 1.9%，max condition coverage 1.1%。
  - 三个 runtime 100% 类合计：46/46 coverage commands success。
- 已完成首个包含 runtime 失败测试的 coverage 验证：
  - `NumberUtils.createNumber`：`coverage_check_auto_createnumber_v1`。
  - coverage 分类结果：40/41 covered，1/41 test_failed，coverage success rate 97.6%。
  - max line coverage 17.1%，max condition coverage 9.5%。
  - coverage 分类与既有 runtime 结果 40/41 一致，证明 runner 能区分覆盖率成功和测试失败。
  - 唯一失败方法：`test_suffix_D_infinite_falls_to_big_decimal`。
  - 该失败方法仍产生覆盖率指标：line coverage 14.4%，condition coverage 6.8%，但 Defects4J 输出 `WARNING: Some tests failed`。
- 已完成第二个包含 runtime 失败测试的 coverage 验证：
  - `NumberUtils.createBigInteger`：`coverage_check_auto_createbiginteger_v1`。
  - coverage 分类结果：20/25 covered，5/25 test_failed，coverage success rate 80.0%。
  - max line coverage 8.5%，max condition coverage 2.4%。
  - coverage 分类与既有 runtime 结果 20/25 一致。
- 已完成第三个包含 runtime 失败测试的 coverage 验证：
  - `StringUtils.substringsBetween`：`coverage_check_auto_substringsbetween_v1`。
  - coverage 分类结果：15/18 covered，3/18 test_failed，coverage success rate 83.3%。
  - max line coverage 1.5%，max condition coverage 0.9%。
  - coverage 分类与既有 runtime 结果 15/18 一致。
- 已完成第四个包含 runtime 失败测试的 coverage 验证：
  - `CsvEscaper.translate`：`coverage_check_auto_csvtranslate_v1`。
  - coverage 分类结果：5/7 covered，2/7 test_failed，coverage success rate 71.4%。
  - max line coverage 63.6%，max condition coverage 16.7%。
  - coverage 分类与既有 runtime 结果 5/7 一致。
- 已完成 `ClassUtils.getPublicMethod` 的 coverage 验证：
  - `coverage_check_auto_getpublicmethod_v1`。
  - coverage 分类结果：2/7 covered，4/7 test_failed，1/7 coverage_failed，coverage success rate 28.6%。
  - max line coverage 11.7%，max condition coverage 0.4%。
  - covered 数量与既有 runtime 结果 2/7 一致；新增 `coverage_failed` 需要保留日志原因。
  - 唯一 coverage_failed 方法：`testGetPublicMethodSecurityException`。
  - 原因：Defects4J/Ant coverage harness 抛出 `java.security.AccessControlException: access denied ("java.lang.RuntimePermission" "setIO")`，导致 `Couldn't obtain coverage results!`。
- 已固定两类自动化 coverage 证据包：`/root/rq1_pilot_real_v2_coverage_two_classes_20260613.tar.gz`，大小约 61K。
- 当前 coverage 证据分层：
  - `/root/rq1_pilot_real_v2_coverage_pilot_20260612.tar.gz`：手动 coverage pilot。
  - `/root/rq1_pilot_real_v2_coverage_auto_v4_20260613.tar.gz`：`LocaleUtils` 自动化 coverage 成功版。
  - `/root/rq1_pilot_real_v2_coverage_two_classes_20260613.tar.gz`：`LocaleUtils` + `DateUtils` 两类自动化 coverage 成功版。

## 2026-06-12 当前推进状态

- 已在 AutoDL 找回 `rq1_pilot_real_v2` 结果目录，包含 10 个真实 Defects4J Lang-1b 方法的生成测试、`summary_table` 和 `analysis_table`。
- 已确认 `rq1_pilot_real_v2` 编译阶段结果：10/10 `completed/success=true`。
- 已重新打包编译阶段证据：`/root/rq1_pilot_real_v2_20260612.tar.gz`。
- 已恢复 AutoDL Java 11 环境，`/root/defects4j-work/Lang-1b` 下 `defects4j compile` 成功；`defects4j test` 有 Defects4J buggy 版本预期失败用例 `NumberUtilsTest::TestLang747`。
- 已补充自动化运行阶段验证脚本：`scripts/run_defects4j_generated_tests.py`。
  - 脚本会给生成测试类加 `D4jGenerated` 前缀，避免覆盖 Defects4J 原测试类。
  - 脚本支持 `--java-home`，用于强制 Defects4J 子进程使用 Java 11，避免 AutoDL `PATH` 中 Java 17 抢先。
  - 缺少 package 的生成测试可通过 `--default-package org.apache.commons.lang3` 补齐。
- 已在干净 checkout 的 `/root/defects4j-work/Lang-1b` 上运行 `runtime_check_auto_v5`：
  - Runtime Pass Rate：128/170，75.3%。
  - `LocaleUtils.toLocale`：25/25。
  - `NumberUtils.createNumber`：40/41。
  - `CreateBigInteger`：20/25。
  - `StringUtils.getLevenshteinDistance`：13/13。
  - `DateUtils.isSameLocalTime`：8/8。
  - `ClassUtils.getPublicMethod`：2/7。
  - `ClassUtils.getShortClassName`：0/13。
  - `CsvEscaper.translate`：5/7。
  - `StringUtils.substringsBetween`：15/18。
  - `ExtendedMessageFormat.applyPattern`：0/13。
- 当前已经形成两层 RQ1 pilot 证据：Compilation Pass Rate = 10/10；Runtime Pass Rate = 128/170 generated test methods。
- 已固定 runtime v5 证据包：`/root/rq1_pilot_real_v2_runtime_v5_20260612.tar.gz`，大小约 190K。
- 已新增简报文档：`docs/RQ1_PILOT_RUNTIME_REPORT.md`。
- 已完成 `LocaleUtils.toLocale` 的覆盖率 pilot：
  - Defects4J coverage 支持 `defects4j coverage -t <Class::method> -i <instrument_classes>`。
  - 必须强制 Java 11：`JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 PATH=/usr/lib/jvm/java-11-openjdk-amd64/bin:$PATH defects4j coverage ...`。
  - 覆盖率日志目录：`experiments/runs/rq1_pilot_real_v2/coverage_check/localeutils_methods`。
  - 覆盖率汇总：`experiments/runs/rq1_pilot_real_v2/coverage_check/localeutils_coverage_summary.csv` 和 `.md`。
  - 覆盖率证据包：`/root/rq1_pilot_real_v2_coverage_pilot_20260612.tar.gz`，大小约 22K。
  - 单测试方法行覆盖率范围：4.1% 到 21.4%；条件覆盖率范围：1.4% 到 20.8%。
  - 高覆盖示例：`D4jGeneratedLocaleUtilsToLocaleTest::test_valid_language_country_variant`，行覆盖率 21.4%，条件覆盖率 20.8%。
- 已新增覆盖率自动化脚本：`scripts/run_defects4j_generated_coverage.py`。
  - 复用生成测试安装逻辑，自动添加 `D4jGenerated` 前缀，避免覆盖 Defects4J 原测试。
  - 支持 `--java-home` 强制 Java 11。
  - 支持 `--include-class-name`，可先只跑 `LocaleUtils`，避免一开始直接跑满 170 个 coverage 命令。
  - 输出 `coverage_summary.csv`、`coverage_summary.md` 和 `coverage_class_summary.md`。
  - 已修复 `--instrument-class` 自动生成文件的相对路径问题，传给 Defects4J 时使用绝对路径。

## 2026-06-11 实验方案调整决策

- 已决定收缩当前论文实验范围，优先形成可交付、可解释、可运行的实验闭环。
- 主实验聚焦 `Defects4J`，使用 DCCI 筛选高依赖复杂 Java 方法。
- `MACO 41` 不作为主实验数据，而作为对齐实验：若作者提供原始清单，则使用 `MACO original 41`；若未提供，则按 MACO 论文 MDCI 规则构建 `MACO-aligned 41`。
- 当前实验删除/后置：`SF110`、`ChatUniTest` 可运行实验、`w/o EvoSuite`、`w/o AssertionEnhancer`。
- `EvoSuite` 降级为传统自动测试生成 baseline，不再作为 `Ours Full` 的内部模块。
- 断言增强、Mutation Score、Assertion Quality 不作为当前主线指标，放入补充实验或 Future Work。
- 当前保留的正式 baseline：`EvoSuite`、`RAG + LLM`、`Ours Full`。
- 当前保留的核心消融：`w/o Knowledge Graph / LightRAG`、`w/o StaticGuard`、`w/o Feedback Repair`。
- 下一步优先任务：
  - 联系 MACO 作者获取原始 41 方法。
  - 固定 Defects4J 主实验方法集。
  - 实现测试运行通过率和覆盖率统计。
  - 构建 MACO-aligned fallback。

## 2026-06-07 已完成的任务

- AutoDL 继续使用昨天同一台实例，项目、Defects4J 和实验结果均保留。
- AutoDL Java 环境切到 Java 11，Defects4J v3 可用。
- Defects4J `Lang-1b` checkout 与 `defects4j compile` 成功。
- 真实方法候选采集完成：从 `Lang-1b/src/main/java` 自动扫描出 1006 个候选方法。
- DCCI 评分跑通，遇到 parser 不支持的候选时使用跳过式评分继续推进。
- RQ1 real pilot v1 跑通：2 个 Defects4J 真实方法，2/2 生成可编译测试。
- 修复真实 Defects4J 场景中 JUnit5/JUnit4 不匹配问题：Defects4J 目标默认使用 JUnit4 prompt。
- RQ1 real pilot v2 跑通：Defects4J Lang-1b，10 个真实方法，10/10 生成可编译 JUnit 测试。
- 已在 AutoDL 打包结果：`/root/rq1_pilot_real_v2_20260607.tar.gz`。

## 2026-06-06 已完成的任务

- AutoDL 环境验证完成。
- GitHub 仓库推送完成。
- DCCI 评分与方法筛选工具加入。
- LLM 输出、编译链路、Maven classpath、空输出检测修复。
- 9 方法 demo pilot_v2 输入数据创建并推送。
- 一方法 pilot 与 9 方法 demo pilot_v2 在 AutoDL 跑通。

## 新增/修改的重要代码

- `scripts/summarize_run.py`
- `tests/test_summarize_run.py`
- `experiments/method_lists/rq1_pilot_real.template.json`
- `src/agents/generation_agent.py`
- `src/core/pipeline.py`
- `tests/test_generation_agent.py`
- `docs/AUTODL_EXPERIMENT_GUIDE.md`
- `scripts/autodl_setup.sh`
- `scripts/autodl_smoke.sh`
- `src/metrics/dcci.py`
- `scripts/build_method_list.py`
- `scripts/run_defects4j_generated_coverage.py`
- `src/utils/llm_output.py`
- `src/core/llm_client.py`
- `src/utils/compiler.py`

## 实验数据与结果

- `rq1_pilot_v2.json`：9 个 demo 方法，AutoDL 已跑通，结果均 `completed/success=true`。
- `rq1_pilot_real.json`：2 个 Defects4J Lang-1b 真实方法，结果 2/2 编译成功。
- `rq1_pilot_real_v2.json`：10 个 Defects4J Lang-1b 真实方法，结果 10/10 编译成功。
- RQ1 real pilot v2 修复轮数：
  - 6 个方法第 1 轮编译通过。
  - 3 个方法第 2 轮编译通过。
  - 1 个方法第 3 轮编译通过。
- RQ1 real pilot v2 涉及的主要修复问题：
  - Mockito 依赖不匹配。
  - 符号缺失。
  - Java 兼容性 warning。
- 当前结果证明真实 Defects4J 方法上的“生成、编译、反馈修复”链路已打通。
- 目前已验证到 compilation success、runtime pass rate、一个方法类的手动 coverage pilot、三个 runtime 100% 方法类的自动化 coverage，以及三个包含失败测试类的 failure-aware coverage；后续还需要扩展覆盖率统计、断言质量和 mutation score。

## 当前进度判断

- 云端 demo 链路已跑通。
- 真实 Defects4J pilot 链路已跑通。
- 当前第一阶段已经具备导师展示的初步实验闭环证据：
  - DCCI 筛选。
  - 真实方法列表。
  - 批量生成。
  - 编译反馈修复。
  - 结果汇总表。
- 目前尚不是最终论文 benchmark，因为还缺运行通过率、覆盖率、断言质量、mutation score 和更多数据集。

## 第一阶段剩余任务

- 生成 RQ1 real pilot v2 结果分析表：方法、DCCI、生成长度、修复轮数、是否成功、修复/失败原因。
- 补充测试运行阶段，不只停在 `javac` 编译成功。
- 扩展覆盖率统计：优先沿用 Defects4J 自带 `coverage`，目前已完成八个 pilot 类，其中三个全通过类、四个包含失败测试类、一个含 coverage_failed 分类；下一步先定位 `ClassUtils.getPublicMethod` 的 coverage_failed 日志，再继续剩余 pilot 类。
- 设计断言质量统计字段。
- 后续再接 PIT mutation score。
- 扩展真实数据集：Defects4J 更多项目、MACO 41、SF110。
- EvoSuite wrapper 接入。
- 导师展示材料整理。

## 下一步

1. 在 AutoDL 保存并检查 `rq1_pilot_real_v2` 证据包：
   - `/root/rq1_pilot_real_v2_20260607.tar.gz`
   - `experiments/runs/rq1_pilot_real_v2/summary_table.csv`
   - `experiments/runs/rq1_pilot_real_v2/summary_table.md`
2. 生成 `rq1_pilot_real_v2` 结果分析表。
3. 补一个 failure/repair reason 聚合脚本或手工表。
4. 扩展 coverage pilot：定位 `NumberUtils.createNumber` 唯一 test_failed 方法并保存证据，然后继续覆盖剩余 pilot 类。
5. 为导师展示整理 6 页左右材料。

## 使用提醒

- 这份文件主要服务新开 Codex 对话时快速恢复上下文。
- 本归档写在外层 `D:\lunwen test\AGENT.MD`。
- 内层仓库也有一份同步归档：`D:\lunwen test\lunwen-test\AGENT.MD`。
- 不包含 API key 或敏感配置。
- 不要把外层 `D:\lunwen test` 和内层 `D:\lunwen test\lunwen-test` 混用：内层是实际推送到 GitHub 的仓库，外层是当前工作区归档位置。
