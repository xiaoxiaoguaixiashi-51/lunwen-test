# 新KCF反馈：逐轮精确执行覆盖

2026-10-30。工程计分修正，不是新研究机制，不新增RQ或消融定义。

## 新旧入口

`scripts/run_kcf_utg_feedback.py` 自动启用 `--exact-exec-union`。调用者还须明确提供 `--passing-only`、`--exact-reference-root`、`--reference-xml-root`、`--seed-execution-roots`。未提供就停止，不静默采用旧XML计数。旧脚本 `run_stage_b_ours_full_feedback.py` 的默认XML模式仅保留历史复查能力。

exact-reference-root须包含reference_manifest.json与xml/；reference-xml-root必须正好指向该xml/。原始seed execution roots是能找到完整exec、JUnit日志和原XML的执行目录，而不是只含复制XML的认可目录。

`--max-rounds 0`只计算认可种子的第0轮：读取配置/固定数据、输出元数据与精确评分，但不构造LLMClient。它适合预算冻结前的离线核验；大于0且确有缺口时才初始化模型客户端。此参数不是新的付费运行授权。

## 每轮协议

1. 校验认可XML索引、源代码哈希、main classes类树及参考XML、固定JaCoCo工具；原始执行须为正数测试的通过JUnit套件。
2. 将认可XML与明确执行路径、exec/JUnit哈希形成索引。XML完全相同但指向多次执行时，仅允许索引明确指定并核对了执行路径；没有这种证据则继续拒绝歧义。
3. 对每项目合并真实exec探针，再只用冻结main classes生成一次报告；无认可执行的项目报告零覆盖，保留参考分母。
4. 把新报告写到coverage_roundN，下一轮直接读取该detail选择缺口。分支互补导致覆盖完成时，目标自然退出缺口集合；没有新增“零增益强制早停”等研究协议变化，仍保留原max-rounds/无缺口停止规则。
5. 每轮probe_union_roundN单独保存认可索引快照、原执行哈希及JaCoCo日志。轮后索引追加不覆盖旧快照，评分期间输入变动则报错。

失败测试、完整性检查拒绝、修复后待语义复核产物仍不能贡献主覆盖。保留既有初始增量通过性准入方式，不把本次计分修正误称为“每份初始测试都完成独立语义审查”。真正批准的修复可在后续明确复核阶段纳入，不能只因为JUnit通过就自动降低门槛。

## 测试和现有数据重放

真实Java互补分支回归：轮0覆盖1/2，轮1合并2/2；轮1之后缺口为空且分母不变。测试同时运行实际feedback main的max-rounds=0，并把LLMClient替换为一旦构造就报错的桩，保证零轮路径不触发模型初始化。合成collector使用JUnit日志夹具，明确不当成真实生成质量实验。

真实已有六目标数据经新入口的共享实现重放：3套认可种子为39/136行、14/90分支；加入已有2套认可增量后为57/136、29/90。只有CSV退出缺口集合，其余有缺口目标仍保留。末轮与之前独立exec后处理一致，没有新增生成请求。这不证明旧XML最大值普遍正确，互补分支回归已经显示两者可不同。

证据位于results/probe_round_scoring_20261030。本批API调用0，不是正式41方法RQ1/RQ2，也不用于证明知识检索或候选适用性机制有效。

## 剩余工作

基线执行目录隔离、append=false、共同main classes报告及通过性统计仍需对齐；非API总成本、正式预算/重复协议和样本使用边界仍未闭合。计分基础设施完成不等于实质贡献已成立，也不自动恢复任何已取消的研究路线。
