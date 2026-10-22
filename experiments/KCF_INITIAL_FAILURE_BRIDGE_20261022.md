# 初始失败修复到覆盖反馈的工程桥接

本次是返工中的运行链路修复，不新增 RQ、消融定义或知识适用性筛选机制，也不沿用历史结果证明新代码有效。旧 runner 默认行为保留供追溯；新试跑显式采用通过套件计分模式。

## 缺口与修复边界

初始 Pipeline 只进行编译修复；原反馈 runner 从 XML 覆盖缺口挑选目标，未主动修复初始运行失败，并会合并失败增量套件的 XML。即便执行覆盖达到 100%，测试失败仍应进入失败修复，不允许被覆盖百分比跳过。

新入口 `scripts/run_kcf_seed_failure_repair.py` 根据实际编译/JUnit 状态直接选择已有失败套件。先核对完整目标 ID、冻结源码 SHA、已生成测试和日志；缺失/超时/环境失败先报错，不自动交给模型。已通过的套件不发请求；每个失败套件最多一次修复请求，保持原类名和原测试方法，保存原件、失败日志、提示上下文、检索记录和独立执行结果。

对于本轮六项目，输入是已保存的两张 coverage summary，合并后有 2 个通过套件和 4 个失败套件。先 `--dry-run` 记录计划，确认 4 个待修复目标与原实验一致；实际试跑最多 4 次模型请求，不再初始生成、不启动 41 方法比较。

## 项目上下文、消融与判分

- 在失败提示中保留有界的被测源码。StaticGuard/项目约束开启时，补充从固定项目源码读取的直接 import / 同包父类型声明、构造入口及方法签名，记录文件和 SHA。信息可能被截断，不把未显示的声明视为不存在；不改知识库、不排除知识条目，也不做完整路径求解。
- 这项声明上下文属于本版本项目约束组，A3 显式关闭；普通被测源码仍提供。A3 从来是整组约束消融，不能把效果单独归因于其中一个检查。没有擅自改成新的消融问题。
- Full/A2 在初始失败阶段使用相同失败检索；A1 需传 `--disable-failure-repair-retrieval`；A3 需传 `--disable-static-guard`。后续覆盖反馈的 A1/A2 CLI 开关仍照原定义。两阶段均需记录实际开关，不能仅凭 YAML 推断。
- 检查修复是否删除/重命名 @Test、减少断言/预期异常检查、添加 Ignore/Disabled/Assume、直接 return 或常量布尔断言。该检查是所有版本共同的评估完整性要求，不随 A3 关闭；它不是语义等价或正确 oracle 的证明。
- 运行通过的修复先放在 `review_xml`，标记 `semantic_review_required=true`，不自动纳入有效覆盖。必须复核断言/异常预期更改是否有源码依据。原失败套件及全部成本始终保留，不能通过删除断言、简单抄实际输出或换目标来制造通过。
- 未改动的初始通过套件放在 `accepted_xml` 并写 XML 哈希索引。KCF 反馈新运行传 `--passing-only`：要求闭合、哈希一致、无待复核条目的种子索引，输出目录必须全新；失败的增量 XML 不合并。被修复的增量套件仍标待复核，其 XML 不自动合并。旧命令未带此开关时保留历史行为，不可与新计分口径混称。
- 新模式每次增量/修复使用独立的 classes/log/exec 目录，JaCoCo 明确 append=false，避免把先前失败执行的数据混入通过套件；旧默认目录行为保留。新模式的增量生成与失败修复共用同一有界源码上下文，A3 同样关闭依赖声明补充。

## 命令模板

```bash
python scripts/run_kcf_seed_failure_repair.py \
  --method-list experiments/method_lists/kcf_six_project_pilot_20261022.json \
  --coverage-summary experiments/runs/six_project_pilot_20261022/coverage/ours_jacoco_summary.csv \
  --coverage-summary experiments/runs/six_project_remaining4_20261022/coverage/ours_jacoco_summary.csv \
  --projects-root /root/maco-aligned-projects --config config/private/kcf_full.yaml \
  --output-dir <fresh-output> --dry-run
```

确认 dry-run 后使用另一个新输出目录并去掉 `--dry-run`，最多针对四个现有失败套件各请求一次。沿用同一 deepseek-flash 非思考设置、SDK 重试 0、8192 输出 token 上限及 Java 8。复核后的 accepted XML 才能作为 `run_kcf_utg_feedback.py --passing-only` 的 round 0；固定参考分母参数仍然必须提供。
