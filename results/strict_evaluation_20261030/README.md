# 共同执行层验证证据

代码提交9e33e8e。云端完整回归200项全部通过，无跳过；本批不发送生成API请求。

strict_eval_fixture_20261030.tgz包含三个真实执行器运行同一手写Java/JUnit夹具的来源、生成副本、class、exec、XML、策略哈希、编译/运行日志及阶段计时。SHA-256为85d00b4b9177b8b097a606e48ea1c67b0f40a9ff9ca29d11be473f16bcc22a51。summary.json单独提供便于审查；regression.log是完整回归输出。

三个执行器均报告p/T类、1个覆盖和1个未覆盖分支。夹具不是正式模型实验；EvoSuite输入是手写的适配测试，不是EvoSuite生成质量证据。没有把本批结果混入旧RQ1/RQ2。

执行规则、使用参数、历史产物错误修正及成本统计限制详见../../docs/STRICT_EXECUTION_POLICY.md。readiness_v4.json是离线准备审计，仍标记formal_run_ready=false；保留所有历史审计版本。
