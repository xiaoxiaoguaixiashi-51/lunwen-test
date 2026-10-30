# 三种方法的共同执行与计分口径

2026-10-30。执行层修正，保持RQ1/RQ2定义及各基线独立生成流程。

## 启用方式

RAG+LLM执行入口scripts/run_stage_b_rag_llm_coverage.py，以及EvoSuite执行入口scripts/run_stage_b_evosuite_coverage.py，均增加`--strict-evaluation --evaluation-reference-root <冻结参考目录>`。EvoSuite另须`--method-list <冻结方法清单>`，将类级执行映射到目标方法。其他必填参数沿用各入口的--help。每次使用全新的output-dir，不能覆盖旧结果。

新KCF入口scripts/run_kcf_utg_feedback.py通过精确exec并集模式自动使用共同执行规则；参考目录由--exact-reference-root提供。认可种子、passing-only和逐轮合并要求见EXACT_FEEDBACK_ROUND_SCORING.md。旧入口默认历史模式，不代表新正式实验已启用严格口径。

## 共同规则

- 每套测试使用新编译/执行目录及append=false，避免旧exec或旧class污染。
- 校验冻结main类树、参考XML及JaCoCo CLI哈希；报告只扫描项目main classes。项目原test-classes不加入编译/运行路径。
- 相同工具JUnit优先；项目依赖与Ant项目lib仍可用于编译/执行。依赖解析采用延迟缓存，避免每条目标重复调用Maven；计时记录缓存命中。
- 只复制生成Java文件，不把输入目录中的其他配置带入执行目录。EvoSuite既有separateClassLoader适配仅作用于副本，原生成文件保留。
- 只有JUnit报告正数测试、零失败且覆盖报告有效的套件进入认可索引。失败XML保留诊断用途，不贡献主覆盖；缺失/失败目标仍按冻结分母计零。
- EvoSuite同类一次执行可对应多个目标方法，保留显式来源；不能把共享执行成本重复计为多份。

没有向独立RAG基线加入KCF多智能体、StaticGuard或反馈修复。JUnit通过也不等于所有初始断言已经人工语义复核。

## 验证与修正

云端Java8/JUnit/JaCoCo真实工具链运行200项回归测试全部通过，无跳过。手写同一条件分支夹具分别通过三个真实执行器，均为1个覆盖分支、1个未覆盖分支，报告中仅有p/T；刻意放入test-classes的无效Leak.class未进入报告。

该夹具包含实际编译、JUnit运行及JaCoCo报告，但EvoSuite输入同样是手写夹具，不是EvoSuite实际生成实验，也不是三个方法的质量对比。API调用为0。原始源码、class/exec/XML、日志、执行策略哈希与各阶段计时归档在results/strict_evaluation_20261030。

核验中修复两类执行产物问题：合法单行Java源码的package解析；RAG保存文件时擅自给FooSpec/FooTests追加Test后缀，导致文件名与public类名不一致。现在保留实际public类名，包含final等修饰符的声明。没有修改生成测试逻辑，也未覆写历史文件；历史结果受到这些问题影响的范围尚未量化。

execution_timings.jsonl覆盖复制、策略校验、依赖解析、编译、JUnit及报告阶段。它不包括完整生成、检索、人工复核或API费用；因此尚不能宣称全部计算预算公平。正式预算、重复次数、严格执行配置、样本使用边界及实质方法贡献仍待闭合，正式运行准备状态仍为false。
