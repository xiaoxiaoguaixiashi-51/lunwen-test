# 阶段成本记录验证

2026-10-30，代码03dc913。云端完整203项测试全部通过、无跳过；日志phase-regression-20261030.log。真实API调用0。

phase_cost_evidence_20261030.tgz的SHA-256为46653dbc6b7f0e251e38f7137053c3b9edbed4694542682da3f79151e3701700，本地与云端一致。71份归档文件已扫描常见密钥/私钥模式，无命中；不包含私有API配置。

归档分两类证据：

- phase-cost-smoke-20261030内含真实Pipeline及独立RAG控制流的阶段追踪、汇总和手写输出。供应商和编译器均为假对象，socket被禁止；计时只用于验证记录能力，不能作模型或编译性能结果。
- experiments/runs/probe_feedback_timed_v1_20261030内含对既有认可产物的真实JaCoCo重放，含原执行来源哈希、每轮认可索引快照、合并exec/XML和固定分母报告。两轮为39/136→57/136行、14/90→29/90分支，与此前计分一致；没有新生成或修改认可条件。

cli_summary.json为假对象流程的分项目阶段汇总，replay_phase_summary.json为两轮真实评分的计时汇总（累计约5.03秒）。两者均无未闭合span，仍明确full_compute_cost_known=false。它们不是完整实验预算，不能把嵌套inclusive_seconds、API elapsed和Java计时直接相加。

实现拒绝重复事件和缺失/循环父链；未结束的start计为未知。API日志通过phase_span_id关联所属阶段。正式重跑协议草案在docs/FORMAL_RERUN_PROTOCOL_DRAFT.md，数值预算、重复次数、样本边界及实质贡献仍未冻结或成立。
