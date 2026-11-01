# 签名上下文简单基线：离线完成，尚未真实生成（2026-11-01）

本轮补齐了此前弱上下文遗漏的声明类API、祖先类/接口声明、构造重载及直接依赖API签名，并发现“首轮提示不超限”仍不足以保证后续阶段合规。本轮API请求为0，未修改生产Pipeline、正式RQ/消融、模型或12000输入上限，没有确立新创新点。

## 实现与来源

`scripts/source_api_context.py` 在明确的main-source根目录和封闭SHA清单上索引源码。保留精确目标方法体，加入声明类和可解析祖先的非private方法/构造声明，再按预算整块加入直接语法类型候选的API。保留可见性、重载、参数及异常声明，字段仅给出擦除类型/名称；方法体、初始化、Javadoc和行为前置条件不在API块中。

它不是Java类型检查器、完整调用图、继承义务求解器或传递依赖闭包。名称冲突、JDK或外部库中未索引的类型均明确记为未解析，不等于不存在。可选API块放不下就记录排除；目标方法和声明类/祖先块不截断，必要块超限会标记未通过。

本地恢复了156个main-source文件。Commons CLI来源为固定版本[1.5.0源码包](https://repo.maven.apache.org/maven2/commons-cli/commons-cli/1.5.0/commons-cli-1.5.0-sources.jar)；JDom来源为此前保存的 `jdom-2e946f814b5ea255c0a5f861a61f911b83bad28a` 源码归档。两个目标Parser/Element文件SHA均与冻结v2方法清单一致；新增记录了全部依赖源码SHA，但云端依赖源码及编译类的一致性尚未核对。不能将匹配两个目标文件写成整个环境已经一致。

官方分词器按[DeepSeek离线计数说明](https://api-docs.deepseek.com/quick_start/token_usage/)重新获取，tokenizer JSON SHA与既有协议完全一致，仍为 `89085f12ef79460ac5f66d1119325ddfc694b4ab209d80bbd81d35f081dc9614`。本地tokenizers为0.22.2；没有执行下载包内的Python代码。计数为离线估计，不是提供商usage。

## 预算结果

F1/F2定义沿用此前开发诊断。F3为F1加上述API签名；最初用首轮上限减4000留出后续空间，两个目标均能加入全部候选API。但使用此前保存的F1分析/规划输出回放后，Element生成提示仍会超限。

|目标|F3首轮Task|F3规划回放|F3生成回放|
|---|---:|---:|---:|
|Parser.processArgs|3112|7068|9633|
|Element.getNamespacesInScope|6214|9322|13950|

发现超限后，另做了明确标记的探索性工程检查：下游只嵌入 `static_analysis` 和 `llm_analysis`，省去重复的 `raw_llm_response`；原始响应仍保存在历史证据中。该视图对F1/F2/F3统一计数，不只给新基线使用。省去原始文本可能丢失解析结果以外的信息，不声称语义完全等价。仅做这一步时Element/F3生成回放仍为12721，仍超限。

进一步按相同保存输出检查全部阶段，并预留512 token，在不截断必要块的前提下整块选择可选依赖API：

|目标|Task|规划回放|生成回放|
|---|---:|---:|---:|
|Parser（按阶段预算选择）|3112|5399|7964|
|Element（按阶段预算选择）|4938|6817|11445|

Parser保留8类API；Element保留Element、Content、Parent、CloneBase、NamespaceAware、Namespace，排除Attribute、AttributeList、ContentList，均有明确记录。这个选择规则是在发现原F3溢出后探索的，不能伪装成预先注册的正式方案。公平的后续开发比较需给所有组相同的解析分析视图、模型及预算。

**后两列使用旧F1分析和规划文本，不是新F3模型输出。** 新的输出长度仍可能触发预算拦截；只完成了离线候选准备，未证明真实生成、编译、运行或覆盖率提高。所有目标仍是已知开发样本。

## 代表性源码核验

机器核验见 `representative_header_checks.json`：Parser的protected abstract flatten签名、Option的3个真实构造重载均已提供；没有把不存在的setValues写成API。Element的addNamespaceDeclaration和Namespace的getNamespace重载已提供，没有虚构addNamespace。

这些签名不包含Namespace保留xml前缀的行为限制，也没有证明错误断言会消失。不能据此宣布对象作用域候选、知识筛选或新约束机制成立；仍需与现有约束/修复及强简单源码上下文区分。

## 验证、归档与复现

本地运行225项回归，222项通过、3项跳过；跳过项依赖本地未配置的真实Java/JaCoCo条件。本轮没有运行云端回归，不沿用此前221项云端通过来证明新代码已在云端验证。原始Windows输出见 `local_regression.raw.log`，便于阅读的UTF-8版本及转码说明一并保存。

`source_api_offline_inputs_20261101.tgz` 保存156个源码、分词器、输入清单、源码许可和3个完整审计JSON。内部164个文件SHA已重新逐一核对；归档SHA256为 `e3a1f46afe7c1d0eab00bcf301ce927f8a7ee22fdf013d19a68ce3ffb4a82493`。未包含私有配置或密钥；见 `archive_verification.json` 和 `input_archive_manifest.json`。

在仓库安装原requirements及tokenizers==0.22.2，将归档解压到新目录后执行：

```text
python scripts/audit_source_api_context.py --inputs-root <解压目录>/signature_inputs --output-dir <新的结果目录>
```

脚本校验原方法清单、原分词器和保存诊断归档SHA，并在socket禁用条件下运行。源码根目录可搬迁，路径显示可不同；目标内容、API选择和上述计数应一致。

已实际仅从归档解压到另一目录重新运行：两个目标的focal/context哈希、全部提示计数和API选择均与原审计一致，API仍为0；见 `archive_replay_verification.json`。

下一步先恢复云端连接，核对依赖源码/编译类和分词器一致性；然后准备对所有组应用同一分析视图的有界真实生成对比。通过前不启动正式41方法实验、不提高预算，也不将普通签名上下文描述为论文创新。
