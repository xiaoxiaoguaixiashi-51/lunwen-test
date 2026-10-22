# 六目标一轮覆盖反馈：运行前冻结

本轮只检验现有 KCF-UTG 的小样本完整链路，不是正式 RQ1/RQ2，不是新增知识适用性机制效果实验，不替换原六个目标。

- 六目标实际 Linux/LF 清单 SHA-256：`94c2ba0a393c5bf7dccfbfc57fcabfab51b0a06d5f1006d7c1138a28c14b1db2`。
- 知识库 SHA-256：`38b5eedac111e59b4d38fcdb2c6e23578b4a3584810a468d94a9db2bc5abace5`；内容不因本次结果修改。
- round 0 为 `seed_failure_repair_20261022/approved_xml` 中的三个通过套件（CLI、Collections、源码复核后的 JDom），起点 39/136 行、14/90 分支。原失败套件和全部此前费用仍保留，不伪装成已解决。
- 六目标都保留在分母里。只按统一的覆盖缺口规则选择增量目标；CLI 已达 14/14 行和 10/10 分支，故无需额外调用。另五个目标有缺口，预计最多 5 次增量生成及各 1 次失败修复，共至多 10 次请求（总安全边界不超过 12 次）。
- 固定 `--passing-only --max-rounds 1 --max-methods 6 --repair-iterations 1 --max-tokens 8192 --timeout 120`；Full 检索与项目约束开启。模型继续使用私有配置中的 deepseek-flash 显式非思考模式、temperature 0.2、SDK 重试 0、请求超时 120 秒和 Java 8。外层总进程上限 1800 秒，不自动付费重跑。
- 失败增量套件 XML 不合并。修复后的套件即便通过仍待源码/断言差异复核，在正式采纳前不合并；不删除/禁用失败断言来提高覆盖率。每次尝试的源码、诊断、classes 和 exec 分开保存，JaCoCo append=false。
- round 1 的增量套件成功不等于修复了原来失败的套件。按目标、套件、测试方法分别统计；原 CSV/Codec/Windward 的失败状态不被新套件覆盖或删除。
- API 用量、失败调用、token、时间全部记录，未知不当作零。输出目录全新：`experiments/runs/feedback_one_round_20261022`。结果经密钥扫描后备份本地/GitHub。

完成后检查覆盖增长来自哪些通过套件、哪些仍失败、是否出现工具链问题与 oracle 修改，再决定下一步。不依据单轮小样本宣称稳定优势或预设论文最终数值。
