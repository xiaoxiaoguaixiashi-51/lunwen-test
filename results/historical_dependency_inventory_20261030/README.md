# 六项目41目标历史证据扩查

2026-10-30。扩展上一轮2方法/6修复对的文本筛查，读取7月5日A3原始执行摘要的全部41个目标及39份保存源码。**这是历史A3材料，不是当前Full的新实验，不将其故障比例用于估计新版KCF。** API调用0，未修改生产生成/检索机制、研究计划或RQ。

## 先把可解释范围分清

| 证据类别 | 目标数 | 解释边界 |
|---|---:|---|
| JUnit No runnable methods | 23 | 测试发现/框架问题，不能当作依赖构造失败 |
| JUnit InvalidTestClassError | 1 | Windward测试类非public/构造器要求不满足，未进入测试方法 |
| 编译失败 | 5 | 包括JUnit/Mockito缺包、符号及类型不匹配，不能统一归为知识错误 |
| 能进入测试后的运行失败，需逐例核查 | 5 | CLI Parser、PatternOptionBuilder、Collections InvokerTransformer、JDom Format、Element |
| 历史报告通过 | 5 | 仅保留历史状态，未用新执行器复验 |
| 缺生成源码 | 2 | 不从样本或分母中静默删除 |

合计41个唯一目标，六项目。自动工具只定位日志信号并记录SHA，不自动判定源码正确性、oracle正确性或知识归因。源码/日志目录按摘要明确路径匹配，不按看起来像的文件名拼接不同运行。

## 两条与依赖构造直接相关的真实线索

1. **CLI Parser.processArgs**：testIteratorAlreadyHasValuesAndOptional在调用parser.processArgs前先调用opt.addValue("existing")；运行日志明确抛UnsupportedOperationException，并说明该方法不供客户端使用。生成注释错误地猜测该API能直接添加值。它说明“符号存在”不等于“该构造/初始化方式可用”；不是目标方法执行后的预期值问题。另一测试的values长度断言失败必须另行分类，不能把整个套件标为同一种原因。
2. **JDom Element.getNamespacesInScope**：testGetNamespacesInScope_DuplicatePrefixes先在同一个Element上添加同前缀、不同URI的namespace，日志报IllegalAddException；后面的目标方法调用尚未到达。生成注释声称该冲突会被忽略，与实际行为不符。该方法其他失败包括排序/数量预期问题，仍需独立区分。

另一个Collections InvokerTransformer案例对反射包装异常cause的断言失败，更接近异常链理解/oracle问题，不因此归入fixture构造。JDom Format的转义/代理字符预期也不能仅因API复杂就算作依赖故障。

以上均来自A3关闭项目约束的运行。当前已有六项目Full试跑中，Parser和InvokerTransformer曾整套通过；因此不能声称这两条旧错误在当前Full中必然复现。Element尚缺当前Full对应生成/执行证据，问题频度和新机制必要性仍未建立。

## 当前固定库的独立构造探针

为避免仅依赖生成注释，对当前冻结JDom main类运行了手写Java8探针（namespace_probe目录），没有模型生成或请求：

| 构造关系 | 实际行为 |
|---|---|
| 同一Element，同前缀、不同URI | IllegalAddException |
| 同一Element，不同前缀 | 成功 |
| 父子Element，同前缀、不同URI | 成功；子对象作用域中自己的namespace可见，被遮蔽的父namespace不可见 |

因此简单规则“重复前缀一律禁止”会误排合法构造，不能把一次冲突记成全局禁令。探针验证的是当前固定库的局部行为；不证明LLM错误频度、新算法收益或与7月二进制完全相同。main类树SHA与固定参考吻合；安装目录无Git元数据，metadata.json如实记录project_revision=null，不捏造现场提交号。源码SHA和完整输出已保存。

## 对创新方向的影响

本批更支持优先研究**依赖对象构造的参数/对象作用域约束**，而非先转向通用断言生成。但这还只是查核线索，不将“调用前失败分流”或“加一条不许重复的提示”当作创新。

下一步必须核对[TELPA](https://arxiv.org/html/2404.04966v2)对象构造/分支依赖分析、[IntTestGen](https://arxiv.org/html/2605.26851v2)协议/状态约束及既有约束输入生成方法是否已覆盖相同问题；需再确认保留约束的Full中是否存在这类失败。若只是A3故意撤掉已有约束导致，或简单源码/前置条件提示已足够，就不开发新层。原“有效检查保持”继续待查，不升格为主路线。

## 可恢复证据

inventory.json保留原归档SHA、摘要位置、41目标的源/日志SHA与可核查错误片段。selected_source_log_inputs_20261030.tgz仅包含该摘要、39份源码及39份对应运行/编译日志，共79份输入和选择清单，不含配置、模型追踪或class文件；常见凭据模式扫描无命中。

选取包SHA-256：a68349f91c1963ff2a8680bdc6b6003b14b24114aa05dc2995ca14954b1f5e6f。用scripts/audit_historical_dependency_failures.py对选取包重新运行，41条case记录和全部分类计数与原归档逐项相同，见replay_verification.json。这是历史输入重放，不是新增实验或把历史覆盖换成新版结果。
