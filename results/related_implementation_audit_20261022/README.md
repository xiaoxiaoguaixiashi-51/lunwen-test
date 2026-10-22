# 近邻实现核查与检索诊断

2026-10-22。本批围绕再投稿的技术贡献判断，未生成测试、未改变生产机制/知识库、未启动付费实验，也不涉及私人投稿通信。公开第三方源码仅在外层本地缓存，仓库只保存出处、固定提交、哈希及我们自己的分析。

## 核查范围与结论

这次不是仅阅读论文摘要：已定位官方仓库固定提交并检查具体函数和调用点。KTester 为 `fce83f1a4b9aa3f1d54598b62027bc17bb585383`，TELPA 为 `b93c4ff610fd3506d760d50767954af7b6713c92`。九个下载文件及 SHA-256 见 `source_snapshot_manifest.json`；其中 base_method/README 为结构与实现说明核查，具体机制结论依据下表源码。未运行第三方代码，不能声称完成基线适配或复现。

| 已读实现 | 具体证据位置 | 对本项目贡献判断的影响 |
|---|---|---|
| KTester 构造上下文 | [code_search.py](https://github.com/SYSUSELab/KTester/blob/fce83f1a4b9aa3f1d54598b62027bc17bb585383/code/tools/code_search.py#L166)：collect_construct_context | 收集构造器、参数类、已有测试和调用示例；我们的依赖声明补充不是此前方法缺失的能力 |
| KTester 用法上下文 | 同文件 collect_usage_context、search_similar_function | 源码签名/依赖与相关函数检索；不能笼统声称现有检索只返回无结构文本 |
| KTester 相似检索 | [CodeSearcher.java](https://github.com/SYSUSELab/KTester/blob/fce83f1a4b9aa3f1d54598b62027bc17bb585383/code/Java/project-index-builder/src/CodeSearcher.java)：search；[IndexBuilder.java](https://github.com/SYSUSELab/KTester/blob/fce83f1a4b9aa3f1d54598b62027bc17bb585383/code/Java/project-index-builder/src/IndexBuilder.java)：ParseSourceCodeInfo | 以调用和字段为索引/查询对象，代码构造 JaccardSimilarityQuery；与本项目对 JSONL 记录全文的词项交集评分不同，但实现不同本身不证明新方法优越或新颖 |
| KTester 分阶段设计 | [generate_prompt.py](https://github.com/SYSUSELab/KTester/blob/fce83f1a4b9aa3f1d54598b62027bc17bb585383/code/procedure/generate_prompt.py)：两个提示入口；[generate_code.py](https://github.com/SYSUSELab/KTester/blob/fce83f1a4b9aa3f1d54598b62027bc17bb585383/code/procedure/generate_code.py)：generate_case_then_code | 先生成结构化案例，再生成代码已经存在；三阶段命名不是足够差异 |
| TELPA Java 分支/调用上下文 | [llm_util_java.py](https://github.com/chenyangyc/TELPA/blob/b93c4ff610fd3506d760d50767954af7b6713c92/telpa_java/utils/llm_util_java.py#L46)：construct_context；[_static_analysis_call_chaining.py](https://github.com/chenyangyc/TELPA/blob/b93c4ff610fd3506d760d50767954af7b6713c92/telpa_java/utils/_static_analysis_call_chaining.py#L603)：find_branch_related、find_call_method | 可见合并分支相关被调方法与所选调用链，并补类声明/构造/字段；“支持 Java、依赖上下文、面向缺口”不是新的差异 |
| TELPA Java 样例选择 | 同 llm_util_java.py 的 select_examples、construct_prompt | 可见按目标覆盖选择有新增行贡献的样例及不同来源提示；不能把检索时机或反馈循环当成首次提出 |

这些证据不足以证明任何工作在所有文件中都没有三值适用性筛选；本报告不从局部代码未出现某函数推断全局不存在。对 IntTestGen 等工作的前轮论文核查仍有效，但本批不把其论文内容冒充本轮代码审计。

## 当前可以确认的区别与不足

本项目知识源是固定 12 条 Lang-1b 人工测试经验，含策略、断言建议和注意事项；KTester/TELPA 在所核查路径主要从当前项目的结构/用法/现有测试组织上下文。这是知识来源与实现路径差异，不是已经证明有效的技术创新。我们的可迁移知识是否真的在更公平的预算下提供额外价值，需要证据。

本项目初始检索对记录全文做 token 交集，并加类名/方法名奖励；失败修复和覆盖缺口阶段使用全文词法交集，没有条件求解或适用性证明。`src/utils/dependency_declarations.py` 只提供有界直接依赖声明，不是可达构造路径合成、完整类索引或知识必要条件判断。

## 新增的离线证据

使用已公开、已扫描的 `seed_failure_repair_20261022.tgz`，读取四个失败种子的原测试、原日志、方法与保存的检索记录。按实际 repair_test 的查询构造重放，四例的 Top-3 **ID 和原始分数全部逐项匹配**，不是根据修复结果猜测查询。输出见 `saved_retrieval_replay.json`；其含归档与知识库 SHA、查询 SHA 和各字段单独查询的排名，不导出原测试全文或 API 配置。

| 失败种子 | 原 Top-3 记录简写与分数 | 已知失败性质 | 可以解释的范围 |
|---|---|---|---|
| CSV printComment | ClassUtils 17、createNumber 16、Calendar 15 | 注释输出计数断言；修复仍失败 | 主题跨度较大，不能据此证明记录冲突或导致失败 |
| Codec colognePhonetic | ClassUtils 12、createBigInteger 11、createNumber 11 | 多项预期值断言；修复仍有失败 | 检索相关性有待标注；不能将所有断言错误归给知识 |
| JDom construct | ClassUtils 12、createNumber 12、createBigInteger 11 | 反射异常预期；修复通过后另做源码复核 | 反射记录有潜在关联，数字解析记录不能直接称必要上下文；修复成功不证明是哪条知识带来效果 |
| Windward html | toMap 19、ClassUtils 19、ExtendedMessageFormat 17 | 类/接口与 API 可用性问题；修复后仍编译失败 | 记录没有明确要求调用该项目的错误 API，尚无可排除的必要能力冲突证据 |

四例均选择 ClassUtils 记录，但重叠词中存在大量共享 Java/JUnit/异常词。例如 CSV 与该记录重叠 17 个 token，其中 16 个仅凭原测试代码就能匹配；测试代码单独查询时该记录得分为 16、仍排第一，完整查询仅比它多 1 分。这不是按词频计数。该现象说明排名由词项集合决定，不能把“得分高”当作已验证的失败机理匹配。JDom 的 NoSuchMethodException 又确有任务关联，不能反过来把所有通用匹配都判噪声。

组件单独查询只是排序解释，既不是在线生成对照，也不是对知识使用的因果消融。四例已用于工程开发，数量很小、来自同一知识库，不估计全数据集的噪声率或失败归因比例。返回了知识不等于模型采用了知识；未采用条目也不自动证明无用。

重放命令（只读已有输入，新的 JSON 输出）：

```powershell
.\.venv\Scripts\python.exe scripts/audit_kcf_saved_retrieval.py --archive results/seed_failure_repair_20261022/seed_failure_repair_20261022.tgz --knowledge experiments/knowledge/dependency_construction_knowledge.jsonl --output <new-output.json>
```

## 对候选机制的决策

当前不进入知识适用性生产原型。旧 261 次 unknown 加上这四个可重放案例，都还没有建立“知识必要条件与目标能力明确冲突，且导致错误”的足够证据。API 误读、oracle 错误与排序相关性不足，是三个不同问题，不能用统一兼容过滤宣称全部解决。

更小的下一步是完成真实条目相关性与使用链标注，并评估现有检索是否优于不按查询选择的简单经验提示或常规检索。此处只是待提出的诊断比较，不是新 RQ、更不是已经批准运行的新消融。它需要预先固定知识、提示长度/预算及选择规则；不能根据这四例修词表后把同四例称独立验证，也不能把换 BM25/TF-IDF 等现成排序本身包装成创新。

正式方法贡献仍未成立。若外部经验在强源码上下文与公平预算下没有可重复的额外价值，应说明证据并提出收缩为系统实证定位的具体建议，而不是继续添加组件维持创新叙事。若有收益，再依据实际失败机理寻找能区别于源码检索和普通约束修复的窄机制。

本批不修改既定 RQ1 三方法和 RQ2 A1/A2/A3，不追加付费 API，不更改模型/知识库/生产检索。报告中的诊断是下一步研究建议，不构成论文正结果、录用保证或路线已变更。

验证记录：本地完整离线回归发现 153 项，152 项通过，1 项因没有设置真实 Java/JaCoCo 工具路径而跳过。新增诊断测试验证确定性并列排序、无正分不返回及保存分数变化必须拒绝重放；四个真实案例的 ID/分数匹配来自实际归档重放，而非假客户端。九个第三方源码快照与公开清单哈希逐项一致。未运行第三方工具或追加模型请求。
