# 已保存修复案例：知识相关性与可观察使用链

2026-10-30；离线人工复核，不调用 API，不改生产检索，不构成新增消融或效果实验。

## 输入和标注口径

输入沿用本目录 `saved_retrieval_replay.json` 的四个案例、Top-3 排名、知识库和归档 SHA-256。原件为 `results/seed_failure_repair_20261022/seed_failure_repair_20261022.tgz`，知识库为 `experiments/knowledge/dependency_construction_knowledge.jsonl`。直接读取归档的 original.java.txt、repaired.java.txt、original_failure.log，对比完整源码差异；未执行归档代码。已有修复状态沿用归档，不声称本日重跑 Java。

本表为单人探索性标注，不是独立双人标注、全数据统计或准确率基准。四例均为开发样本。

- 相关性：具体相关＝知识内容直接涉及已观察到的失败机制；通用相关＝仅有异常、断言、框架等通用建议；未见具体关联＝未找到针对当前失败的具体指导。它不等于已证实无用。
- 使用链：只报告修复源码中可观察变化。内容相似、修复通过或返回条目均不证明模型采用了某条知识，尤其当相同信息已在原测试、错误日志或源码上下文中出现时。
- 适用性冲突：需要知识的必要条件与目标能力明确矛盾。示例的 Lang 类名、旧项目 Java 6 注意事项本身不能证明目标必须提供同名 API 或只能使用 Java 6。

## 12 个案例—条目对

条目缩写均指完整知识 ID：ClassUtils=`commons-lang-classutils-get-public-method`；Number=`commons-lang-numberutils-create-number`；BigInteger=`commons-lang-numberutils-create-big-integer`；Calendar=`commons-lang-dateutils-is-same-local-time`；toMap=`commons-lang-arrayutils-to-map`；Format=`commons-lang-extended-message-format`。

| 案例 | 条目（分数） | 针对原失败的相关性 | 修复变化与归因边界 |
|---|---|---|---|
| CSV printComment | ClassUtils (17) | 通用相关：JUnit/异常；反射和可见性不解释字符计数 | 原修复源码无语义变化，不能确认采用 |
| CSV printComment | Number (16) | 通用相关：断言与异常；数字解析不解释重复字符计数 | 同上；原错误断言仍保留 |
| CSV printComment | Calendar (15) | 未见具体关联：时区、月份和 Calendar 构造不解释 append 调用 | 同上 |
| Codec colognePhonetic | ClassUtils (12) | 通用相关：异常/辅助类；不解释音码规则 | 主要改期望字符串，未见反射策略新增；采用未知 |
| Codec colognePhonetic | BigInteger (11) | 未见具体关联：进制解析不解释音码压缩 | 期望字符串变化不能追溯到 BigInteger 条目 |
| Codec colognePhonetic | Number (11) | 通用相关：具体值断言；不提供音码 oracle | 没有条目中的数值类型断言新增；采用未知 |
| JDom construct | ClassUtils (12) | 具体相关：反射、缺失方法、NoSuchMethodException | 改为检查 NoSuchMethodException，但原日志已直接给出同一异常；不能单独归因知识 |
| JDom construct | Number (12) | 通用相关：期望异常；具体异常为 NumberFormatException，非当前异常 | 未见数字解析策略新增；采用未知 |
| JDom construct | BigInteger (11) | 通用相关：非法输入异常；不是反射构造失败 | 同上，不能解释具体修正 |
| Windward html | toMap (19) | 通用相关：Map 构造/泛型；不说明请求响应的类/接口和构造器 | 泛型和 API 声明有变化，但没有条目要求的数组转 Map；采用未知 |
| Windward html | ClassUtils (19) | 通用相关：可见性/辅助类；不提供 Windward 真实声明 | 类/接口切换不证明采用反射经验；采用未知 |
| Windward html | Format (17) | 通用相关：注册表/格式化；不是 Windward 插件的真实 API | 未见 FormatFactory 或格式模式策略新增；采用未知 |

## 可以直接复查的源码差异

各路径相对于归档顶层 `seed_failure_repair_20261022/cases/`；完整案例 ID 见重放 JSON。

1. **CSV：无语义修复。** original.java.txt 与 repaired.java.txt 唯一差异为末尾换行。`test_printComment_singleLine_newRecordTrue_writesMarkerSpaceAndRecordSeparator` 仍断言 `countOccurrences(calls, "C:l|") == 1`；输入为 `hello`，原日志记录 expected 1 / actual 2。这里存在可以从原测试本身检查的计数错误，所选知识均不提供该字符计数事实。不能将后续其他反馈轮修好的结果混入这一次修复。
2. **Codec：局部改 oracle，仍未全通过。** `CA/CO/CU` 的期望由 `40` 改为 `4`，`CE/CI` 由 `80` 改为 `8`，两处 `BAB` 由 `10` 改为 `11`。原日志还指出 `test_x_after_ckq_codes_8` 的 expected 8 / actual 48；该测试在本次 diff 中没有修改。这解释了“存在修复动作”不等于整个测试套件通过。未重新判定所有音码 oracle 的正确性。
3. **JDom：异常 oracle 实际改变。** `test_construct_interface_instantiation` 从捕获 IllegalStateException / 检查 InstantiationException，改为 IllegalArgumentException / NoSuchMethodException，并检查 `no-arg constructor` 消息。原日志已明确给出后面这组异常和消息，因此 ClassUtils 条目虽具体相关，不能证明其带来了日志以外的信息增量。归档记载修复通过；是否符合目标源码语义沿用此前独立源码复核，而不是仅以运行通过为依据。
4. **Windward：API 声明修正，不是知识冲突的直接证据。** 两个 fake 请求/响应类由 implements 改为 extends，FakeJsonPlugin 由 extends 改为 implements；响应 write 以及 JSON 方法签名改动。仍失败的状态不能证明检索记录造成这些错误；这些条目没有要求以相反的类/接口关系实现 Windward，也没有声明必须调用错误的项目构造器。

## 阶段结论与下一步

本轮补齐 4 例 × 3 条的初步相关性和源码变化检查；**没有任何一条可以确认已建立“知识必要条件冲突 → 生成错误”的因果链**。也不能把“未确认采用”写成“模型从未使用”。当前不开发复杂适用性过滤或失败惩罚机制。

下一项是冻结一个不调用模型的诊断比较规格：现有检索选择、固定通用经验提示及常规排序各自提供什么信息，如何控制上下文长度和生成预算，哪些样本留作独立评估。若要运行在线比较，应先明确处理定义、预算和成功标准；它不替换 RQ1/RQ2，也不能仅以排序改进作为创新主张。正式重跑仍须补齐公平预算与重复运行，本文档不替代这些证据。

这一步由 skilldui 的“先建立条目—代码—错误关联，再判断原型”要求约束；未改研究计划、知识库、模型或既定消融。
