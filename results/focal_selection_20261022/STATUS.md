# 返工：目标方法与固定覆盖率口径

本次修复面向新运行，历史方法清单和历史覆盖率汇总不变。

- 新清单 `experiments/method_lists/kcf_utg_rq1_methods_v2.json` 保留相同 41 个 ID，增加声明类、擦除后的参数类型和源码 SHA-256。
- `TreeList.addAll(Collection)` 仅选外层方法，排除 `AVLNode.addAll(AVLNode,int)`；生成依赖分析与覆盖率评估使用同一选择器。
- `TrieEntry.toString` 的旧顶层类名不存在。依据源码声明与实际 class 文件，显式修正为 `org.apache.commons.collections4.trie.AbstractPatriciaTrie$TrieEntry`；原 ID、源文件和方法未更换。
- 全部 41 项严格匹配成功，歧义数 0；对照记录见 `focal_selection_v2.json`。
- 以已固定六项目编译产物生成不执行测试的 JaCoCo 参考 XML，分母为 **1042 行、776 分支**。历史 1100/802 分母不直接用于新运行。
- 新评估可使用 `--reference-xml-root`，覆盖报告缺失时计零覆盖并保留分母；不一致的行/分支分母报错。严格清单的反馈 runner 要求显式提供参考 XML，并检查缓存口径。
- EvoSuite 1.2.0、JaCoCo 0.8.12 已验证。单目标 OptionGroup smoke 完成生成、编译、JUnit、JaCoCo 和统计，18/18 行、8/8 分支。它仅是工具链验证，不是正式 RQ1 或优势结论。
- 模型调用增加逐目标 JSONL：输入/输出、服务端返回模型标识、token 用量、耗时、失败类型；未知 token 用量保留 null。新 KCF 模板显式禁用 SDK 隐式重试，统一请求超时 120 秒。
- 初始生成和覆盖反馈保存各轮代码及失败快照。API 私有配置采用隐藏输入，放在 Git 忽略的 `config/private/`，目前尚未配置真实 API 或产生模型实验结果。
- 本地项目虚拟环境完整回归测试 127 项通过；真实云端的工具 smoke 通过，模型调用记录测试使用假客户端，不产生付费调用。

JaCoCo CLI 的 report 支持不传 exec 数据、根据编译类生成报告，参考官方说明：https://www.jacoco.org/jacoco/trunk/doc/cli.html 。工具来源与哈希见 `tool_manifest.json`。
