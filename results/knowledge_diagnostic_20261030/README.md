# 知识选择开发诊断：48次请求与统一重评完成

2026-10-30。48次生成请求和绝对路径独立重新评估均完成。原评估器的compile_failed属于路径错误，不用于评估模型；统计只使用独立重评原件。此前运行原件仍原样保留。

用户已自行设置平台关机；我们短暂建立的独立定时器已确认cancelled，没有修改用户平台设置。

生成原件归档为 knowledge_diagnostic_generation_20261030.tgz，SHA-256为3691060a645f9b317c691fb95ae687e0f3b22af06a137b6b8b3b5a0e069a7fb4。独立重评归档 knowledge_diagnostic_reeval_20261030.tgz，SHA-256为6359602dd99e6674bfcfea5c867c8f7065388211fdf87699c3ba63a52943c10a。两份均已下载并与云端哈希匹配，凭据模式扫描没有命中；归档范围仅为两个指定运行目录，没有config/private、SSH凭据或私人投稿文件。追踪写入逻辑还会替换配置中的API密钥，公开前未发现凭据内容。

## 结果：四处理的状态没有差异

N＝无知识，F＝固定三条经验，L＝现有检索，T＝普通TF-IDF排序。每处理包含4方法×3重复，共12套件。

| 处理 | 编译通过 | 完整套件运行通过 | 运行断言失败 | 编译失败 |
|---|---:|---:|---:|---:|
| N | 9/12 | 3/12 | 6/12 | 3/12 |
| F | 9/12 | 3/12 | 6/12 | 3/12 |
| L | 9/12 | 3/12 | 6/12 | 3/12 |
| T | 9/12 | 3/12 | 6/12 | 3/12 |

各处理JDom三次均通过；Codec与CSV各三次均断言失败；Windward三次均编译失败。既不是48个独立方法，也不是正式RQ1/RQ2结果。四个方法之前已用于工程开发，此处只作开发诊断，不报告全数据显著性或泛化。

源码变体数（按完整生成源码SHA，不将字面不同等同策略不同）：Codec共3种，CSV共1种，JDom共1种，Windward共9种。即使产生不同文本，也没有观察到完整套件状态上的优势。

## 通过产物的语义核查

12个JDom通过产物源码完全相同，SHA-256为b281386de7612eae47cd72be8f3a47658e263843ce1789d99603c79ee62fdb7f。与原测试相比，只有test_construct_interface_instantiation的异常oracle变化和末尾换行：改为捕获IllegalArgumentException、检查cause为NoSuchMethodException，并检查no-arg constructor消息；没有删掉该失败测试或通过跳过它获得通过。

已核查的ReflectionConstructor源码SHA-256为9fa28e6f17bc9b97e17ea31078ce3fe83ca3ab63d869a435d65c98de38048a43。源码第85行先调用getConstructor，90–91行捕获NoSuchMethodException并包装为IllegalArgumentException，接口没有公开无参构造器；原测试的IllegalStateException/InstantiationException预期与此路径不符。修正与源码路径吻合，不是仅凭actual值抄答案。已有自动完整性门禁与本次源码diff一致。

这是**一次非盲、单一审查者的源码核查**，不冒充独立多人评审。相同源码可共享该项核查依据，但不是12次独立语义判断。summary.json保留原始semantic_review_required标志，避免改写重评证据；本段补充审查结论不回写原产物。判断仅覆盖这一处oracle修正，不等于证明整套测试能检测真实缺陷。四种处理均得到同一修正，不能将其归因于L的ClassUtils条目；原错误日志本已给出该异常信息。

## 成本和预算

追踪记录48条，48条API状态ok，无SDK重试。输入346581 token、输出123445 token，总计470026 token；输入缓存命中267258、未命中79323。API调用elapsed_seconds相加为372.226132秒，它不是整个实验墙钟时间，也不包括完整源码准备、Java执行和备份。货币扣费尚未独立核对，不虚报金额。

最大实际prompt_tokens为10135，没有请求超过12000输入上限。官方tokenizer离线估计最大10130，固定256封装余量足以覆盖本批观察到的差异；这不证明未来任意请求也精确匹配。两份归档分别包含原生成trace及修正后的Java/JaCoCo证据；没有用原错误路径的结果做成功率统计，也没有因修评估器增加模型请求。

## 阶段判断与后续

本批没有发现按查询选择经验的额外收益，**不支持现在投入复杂的适用性筛选或失败惩罚原型**；但四个开发样本也不足以宣称知识检索普遍无效。CSV重复保留错误断言、Codec局部修正但剩余oracle失败、Windward仍误读构造器和可覆盖钩子，是后续值得分别分析的失败，不能混称为检索适用性冲突。

下一步先整理三类剩余错误的源码依据、补齐正式比较的预算控制与样本使用记录，并据此决定是否提出更小的机制或系统实证定位。未经过独立样本验证，不把本表改写成论文正式消融、不重命名旧实验为新方法结果、不扩大本批48次API授权。

可复算命令：

```powershell
.\.venv\Scripts\python.exe scripts/summarize_knowledge_diagnostic.py --generation results/knowledge_diagnostic_20261030/knowledge_diagnostic_generation_20261030.tgz --evaluation results/knowledge_diagnostic_20261030/knowledge_diagnostic_reeval_20261030.tgz --output <new-summary.json>
```

汇总工具验证48唯一计划单元、调用目标与评估完整性、无重试、输出上限、生成源码和重评源码哈希一致，并扫描明显凭据模式；新增真实归档汇总及输入变更拒绝测试通过。原始逐单元状态及所有失败均公开保留，不挑选最佳重复。
