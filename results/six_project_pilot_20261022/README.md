# 六项目初始生成工程试跑：结果与继续条件

不是正式 RQ1/RQ2，不是新增知识适用性机制实验。使用固定六个 v2 目标，每项目一个；没有运行覆盖反馈和运行失败修复，不能将结果与历史 Full 三轮反馈后的汇总直接比较。

## 结果

| 项目/方法 | 独立编译 | JUnit 运行结果 | 当前观察 |
|---|---|---|---|
| CLI / Parser.processArgs | 通过 | 9 tests，0 failures | 初始编译第二轮通过 |
| CSV / CSVPrinter.printComment | 通过 | 16 tests，1 failure | 先有 JUnit 编译类路径问题；独立 harness 编译通过后发现计数断言 expected 1 / actual 2 |
| Codec / ColognePhonetic.colognePhonetic | 通过 | 31 tests，5 failures | 音码断言的期望值与执行值不一致 |
| Collections / InvokerTransformer.transform | 通过 | 20 tests，0 failures | 初次编译通过 |
| JDom / ReflectionConstructor.construct | 通过 | 13 tests，1 failure | 接口无无参构造器，生成测试的异常预期与实际 IllegalArgumentException 不一致 |
| Windward / AbstractHttpWindwardContext.html | 失败 | 未进入 JUnit | 把 WindwardRequest/Response 当接口 implements、把 JsonPlugin 当类 extends，修复轮次内未消除 |

共 5/6 独立编译通过、2/6 整套测试通过。JUnit 报告共运行 89 tests、7 failures；这与目标级或套件级通过率不是同一个统计单位。CSV 的原 pipeline success=false 与独立编译 success=true 同时保留，不能覆盖其中一个状态。

全部六目标固定分母为 136 行/90 分支。**只纳入通过套件**的保守覆盖率为 25/136 行（18.4%）、12/90 分支（13.3%）；没有剔除失败目标的分母。包含失败套件 XML 的诊断统计为 104/136 行（76.5%）、80/90 分支（88.9%），不得当作通过测试的有效覆盖率。按通过测试方法逐个执行可能得到更细覆盖率，本轮未做该细分；不宣称失败套件内所有测试均无效。

## 环境修复与成本

- API 前补齐了 Ant 项目的已构建 core 类路径。首批运行还暴露初始编译器缺少统一 JUnit 4 的问题，CSV 的模型修复不能解决缺 jar。
- 初批在 Codec 的代码生成请求中发送 SIGINT 停止；原目录保留，不把没有 status 的方法改成完成。首次原始代码提交 `1a56c55`。
- 修复后初始编译器与独立覆盖率 harness 对齐已有 JUnit 4.13.2/hamcrest；不更改项目 pom，StaticGuard on/off 均使用同一环境支持。六项目实际 javac 目标类/JUnit 引用预检全部通过。
- CLI/CSV 复用已有生成代码，仅独立编译运行；剩余四目标在新目录、提交 `2c892fb` 下续跑。
- 两批共 28 次逻辑 API 请求，27 次返回正文，1 次中断未返回 usage。已知 token 合计 257917（输入 189468，输出 68449），**另有 1 次请求用量未知**；不是完整账单或精确费用。API 耗时合计约 221.175 秒，非端到端总耗时。
- 这批成本不包含更早 OptionGroup 单方法 smoke；不能漏掉首批失败和中断来只报告续跑成本。没有追加全量、消融或覆盖反馈的付费请求。

## 实际输入与跨平台换行

Windows `core.autocrlf=true` 造成工作副本 CRLF 与云端 Git checkout LF 的字节哈希不同，但 JSON 内容相同。已下载实际执行字节作为 `executed_pilot_methods.json` 和 `executed_remaining4_methods.json`，未覆盖旧清单或原始数据。

六方法实际清单 SHA-256：`94c2ba0a393c5bf7dccfbfc57fcabfab51b0a06d5f1006d7c1138a28c14b1db2`。
四方法续跑实际清单 SHA-256：`2722747c1d3412ba6a5e0bf5ad0ab028e1c92b9a309e3b4b2fe481ad19f6c788`。
生成器今后显式输出 LF，避免新清单再次发生差异。

## 审计判断与下一步

1. 运行链路已可用，但单方法满覆盖不能代表复杂方法。当前失败同时包含环境依赖、断言/异常预期和依赖类型实体错误，不能统一归因于知识检索。
2. Windward 的类型用错是可追溯真实问题，说明需要核对导入依赖的实际声明/构造入口。它尚不能证明检索条目的必要条件冲突，也没有证明候选适用性筛选比补源码上下文更有效。
3. 初始 Pipeline 目前只做编译修复；失败修复知识检索位于后续反馈 runner，不在初始编译修复中。不能把所有修复阶段都写成有检索。
4. 现有反馈流程根据覆盖缺口选目标；若直接把失败套件的 XML 算作有效覆盖，可能掩盖需要修复的运行失败。先审计并补上运行状态进入反馈的路径/测试，明确通过测试的计分政策；不得只挑容易通过的方法或删除失败断言追高覆盖率。
5. 后续先做上述工程/证据修复及现有 A1/A2/A3 两阶段开关核查，再在同一固定小样本验证完整反馈链路；正式比较仍须统一预算、重复运行和独立评估。当前不扩大到 41 方法付费实验，不替换既有 RQ2。

## 证据

原始包包含输入输出、全部模型调用追踪、各轮源码/编译诊断、JUnit 日志和 XML。导出前已逐文件扫描配置的完整 API key，私有配置未包含在包中。`aggregate` 仅是无模型调用的统计工具输出；它将通过套件 XML 与诊断 XML 分开保存。

本地完整回归 135 项通过；云端同步至 `023bfca` 后同样 135 项通过（3.354 秒），日志见 `cloud_tests.log`。该回归使用假模型客户端，不追加真实模型请求。

| 归档 | SHA-256 |
|---|---|
| `six_project_pilot_interrupted_20261022.tgz` | `9af76b9d8ebc886924ed284dcb93b81d4606a67b7f6e94d4592335f662496564` |
| `six_project_remaining4_20261022.tgz` | `c2e90435f3e7d39e73ddce0d3029bf19ada4ca22c0483ce44b10b205aa19a3fd` |
| `six_project_pilot_aggregate_20261022.tgz` | `f9527204548caa88f8175fb6072fec4f90a6af1f950ae969c9f821008ab129a4` |
