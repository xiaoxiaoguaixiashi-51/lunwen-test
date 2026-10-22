# 六项目工程兼容性试跑（不是正式 RQ1/RQ2）

在观察本轮 API 结果前固定以下六个 v2 目标，不按覆盖结果替换：Parser.processArgs、CSVPrinter.printComment、ColognePhonetic.colognePhonetic、InvokerTransformer.transform、ReflectionConstructor.construct、AbstractHttpWindwardContext.html。每项目一个，覆盖解析、I/O、编码算法、反射、Ant 构建和 Web 框架依赖；不是统计代表性抽样，不据此推断总体效果。此前 OptionGroup smoke 不合并为本轮成功目标。

清单 `method_lists/kcf_six_project_pilot_20261022.json`。Linux 实际运行输入及 Git blob 的 LF 字节 SHA-256 为 `94c2ba0a393c5bf7dccfbfc57fcabfab51b0a06d5f1006d7c1138a28c14b1db2`；Windows 首次生成的 CRLF 工作副本为 `8c5d64c0a33f2323b0b0890e467ab457eb046c07b6ade6a4cfeaffbfdb987894`。两者 JSON 内容相同，不应宣称字节哈希相同；正式复现以每次实际输入哈希为准。保留完整 v2 owner/signature/source SHA-256。后续生成器显式输出 LF 防止新清单重复出现换行差异，不覆盖本轮已冻结文件。

本轮仅验证 KCF Full 的初始生成、编译修复、独立 JUnit 与固定分母覆盖率。**不包括覆盖反馈、对比基线或消融效果检验，也不证明新机制有效。** 模型 `deepseek-flash`，显式非思考模式、temperature 0.2、单请求 max_tokens 8192（生成代理可能显式覆盖，应以调用追踪为准）、SDK 重试 0、请求超时 120 秒、编译最多 3 轮，继承单方法 smoke 私有 Full 配置。三个代理 + 最多三个修复请求，6 个目标最多 36 次逻辑模型请求，外层进程超时 1800 秒；未知 token 不当成零，超时/失败不自动整批付费重跑。

Ant 编译类路径兼容修复在调用前完成：当 Maven 项目根缺失，且存在 build.xml 与已构建 build/core 时，使用 build/core、core/src/java 和 lib 下已有 jar。不引入新测试框架或下载额外项目依赖，StaticGuard 开关不改变这项环境支持。单元测试验证 Ant 下不调用 Maven；真实云端 JDom 编译 smoke 通过后才启动本轮模型调用。

结果必须保留全部六个方法、失败原因、各次请求用量和源码/错误、逐方法覆盖状态；缺少覆盖报告仍保留 canonical 分母计零。先分析编译失败、断言失败与环境失败，后续修复和再跑采用新标记产物，不能删除不利结果。原始证据经私有 key 扫描及人工检查后备份本地并同步 GitHub。云端资源放在数据盘。

后续先审计小样本失败、工程兼容性和成本，再检查两阶段 A1/A2/A3 开关与独立 RAG/EvoSuite 链路，冻结正式预算及重复次数后推进正式比较。

## 初次执行的环境错误与续跑边界

初次执行中 CLI 第二轮编译通过；CSV 三轮均缺少 org.junit，随后在 Codec 的生成请求中人工发送 SIGINT 停止。中断请求若未返回 usage，成本必须标记未知，不能记为零。保留原目录及全部已有状态/请求，不把尚未执行的项目记为失败或完成。

诊断发现初始编译器依赖项目 Maven 测试类路径，而固定 CSV 项目本身不一定提供 JUnit 4；独立覆盖率 harness 原本已为所有方法提供主机 JUnit 4.13.2。修复使初始编译环境也一致使用已缓存 JUnit 4.13.2/hamcrest，不新增下载或改项目 pom，也不把缺 jar 当生成代码错误。该环境支持对 StaticGuard on/off 相同。

六项目均通过实际目标类与 JUnit 的最小 javac 引用检查后，才允许继续付费请求。CLI/CSV 已生成源码只做独立运行与覆盖率评估，不重新付费生成；Codec（被中断）、Collections、JDom、Windward 采用另行冻结的 remaining4 清单与新输出目录，最多再 24 次逻辑请求/1800 秒。这是环境返工续跑，不是独立重复或正式比较。必须合并报告首次和续跑全部实际用量，包括未知成本。
