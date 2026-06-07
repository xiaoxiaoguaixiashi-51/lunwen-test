# 项目当前状态归档

## 基本信息

- 本地外层目录：`D:\lunwen test`
- 本地内层实际推送仓库：`D:\lunwen test\lunwen-test`
- AutoDL 服务器目录：`/root/lunwen-test`
- Defects4J 工作目录：`/root/defects4j-work`
- GitHub 仓库：`https://github.com/xiaoxiaoguaixiashi-51/lunwen-test.git`
- 当前远程 `main` 最新提交：`71497d0 Use JUnit4 prompts for Defects4J targets`

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
- 目前仍只验证到 compilation success；后续还需要补测试运行、覆盖率、断言质量和 mutation score。

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
- 接入覆盖率统计，优先 JaCoCo 或 Defects4J 自带相关能力。
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
4. 开始实现“测试运行通过率”统计。
5. 为导师展示整理 6 页左右材料。

## 使用提醒

- 这份文件主要服务新开 Codex 对话时快速恢复上下文。
- 本归档写在内层仓库 `D:\lunwen test\lunwen-test\AGENT.MD`。
- 外层工作区也有一份同步归档：`D:\lunwen test\AGENT.MD`。
- 不包含 API key 或敏感配置。
- 不要把外层 `D:\lunwen test` 和内层 `D:\lunwen test\lunwen-test` 混用：内层是实际推送到 GitHub 的仓库，外层是当前工作区归档位置。
