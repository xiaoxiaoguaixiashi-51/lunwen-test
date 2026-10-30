# 跨阶段配置预检

2026-10-30。scripts/preflight_kcf_run_plan.py只读取配置与本地tokenizer/知识库文件，不构造LLM客户端、创建预算数据库或启动子进程。通过预检不等于批准运行或确立论文贡献。

先在预定执行机器生成新计划文件：

```bash
python scripts/preflight_kcf_run_plan.py --template-run-root /root/autodl-tmp/NEW_RUN --output plan.json
```

模板有13条LLM阶段任务：Full/A1/A2/A3各初始、种子修复、反馈三阶段，独立RAG只有初始生成。模板的config路径指向尚未创建的新配置，不会复制私有文件或把旧配置变成正式配置。单个草案slot不代表已经决定正式重复次数；模板也不是可执行调度器。

指定各阶段实际使用的config、output_dir及ablation_flags后执行：

```bash
python scripts/preflight_kcf_run_plan.py --plan plan.json --output preflight.json
```

每阶段检查正整数预算、零SDK重试、固定本地tokenizer哈希、显式模型参数、新输出与新账本；同变体所有阶段必须使用同一策略/账本，变体间不得共用账本。还比较KCF各变体的知识库内容、检索数量、编译修复参数和Java设置，校验A1/A2/A3对应CLI开关。它拒绝既有账本，只用于新运行准备，不把恢复运行误判成允许清空数据库。

结果仅保存配置文件SHA和模型/账本身份摘要，不输出供应商地址、API key或配置正文。原始计划中的配置路径仍是用户选择的实际路径，不能将私有配置本身提交GitHub。

configuration_checks_passed只说明所声明的计划在静态检查中一致。尚须核对真正启动命令及有效元数据、所有源文件/工具/参考类树、EvoSuite类级预算和映射、正式预算与停止规则、重复次数和研究证据。formal_run_ready始终为false，不用一份静态计划替代实际运行证据。

现场验证：云端207项回归全部通过、无跳过。将现有Full/A1/A3私有配置映射到13个拟议阶段后，只读检查发现全部缺少request_budget；这些配置仍是此前开发/诊断配置，未自动变为正式配置，也未被写回。配置缺少该节时，本工具跳过后续预算相关检查，不能把其余条件当作已通过。证据见results/run_plan_preflight_20261030。
