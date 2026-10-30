# 非API阶段耗时记录

2026-10-30。补充原有请求预算与执行日志，不改变生成策略、RQ或消融定义。

## 新记录

KCF初始batch、独立RAG、种子修复、覆盖反馈及EvoSuite生成的命令入口自动在输出目录设置phase_calls.jsonl。可通过KCF_PHASE_TRACE_PATH显式指定；直接调用库函数而未设置该环境变量时不写记录。初始任务分析、计划、代码生成、编译反馈、代码修复、知识/源码检索以及逐轮探针合并均有嵌套span。EvoSuite只记录实际启动的类级生成命令，dry-run不伪造执行成本。

记录span_id、parent_span_id、目标、阶段、进程/会话、UTC起始时间及monotonic耗时。start先写盘，正常返回或Python异常写end；进程被杀可留下未闭合start。日志不记录提示词、参数、密钥、异常正文或生成源码。API追踪新增phase_span_id，可以关联所属阶段；旧追踪没有该字段时不补造关联。

python scripts/summarize_phase_costs.py --trace <phase_calls.jsonl> --output <新索引.json>可合并多份完整阶段日志，拒绝重复事件、缺父事件、循环父链、非法耗时与身份变动。只提供截断的子span日志会报错，不能凭空补父。未闭合span标为未知，不填0。

## 避免重复计算

inclusive_seconds是各阶段包含内部操作的时间，不能把Pipeline总时间与其中TaskAgent/API/编译时间相加。sum_completed_root_seconds只累计已完成根span，是累计操作时长；并行操作相加也不等于实验起止墙钟时间，更不是CPU/GPU使用量。returned仅表示Python函数返回，编译是否成功仍看执行状态和JUnit日志。

共同执行器已有execution_timings.jsonl，记录复制、依赖解析、编译、JUnit和JaCoCo报告。它与生成span、API elapsed可能重叠，报告应分项展示并按来源关联，不能直接相加。EvoSuite按project::fqcn记录35个类级任务，依照冻结方法映射关联41目标，不能按方法复制35份任务成本。

## 边界

原历史实验没有新增span，不能事后推算其检索/生成时间。机器初始化、构建准备、调度等待、人工语义复核和未包裹的操作尚未完整测量；阶段日志本身的开销也包含在外层计时中。该索引因此始终full_compute_cost_known=false。不能拿新增日志声称正式公平预算已成立。

本地203项回归通过，3项真实Java工具链测试因本地条件跳过；云端203项全部通过、无跳过。持久化smoke使用真实Pipeline及独立RAG控制流、假供应商与假编译器，并禁止socket，不能当作真实API或Java性能测量。另外以保存产物完成真实两轮JaCoCo探针重放，计时共约5.03秒、未闭合span为0，覆盖仍为39/136至57/136行、14/90至29/90分支；这是本机该次评分耗时，不是原生成总成本。证据见results/phase_costs_20261030。
