# 修复能力保持候选：边界检查

2026-10-30。仅研究候选与本地只读诊断，没有新模型请求、生产算法或新效果实验。方案见docs/CANDIDATE_VERIFIED_CHECK_PRESERVATION_20261030.md。

boundary_check.json含两个不同性质的证据：合成Java文本在保持断言数量时将精确状态检查改为非空，现有结构检查仍ok=true；这段文本只经过AST分析，未编译/执行，不估计真实弱化率。另从固定SHA的真实pilot归档读取Full CSV原/修复源码，结构检查因检查数量下降而拒绝；这条真实线索尚未证明修复语义正确，不能称为确认的误拒。

本轮近邻阅读已发现YATE、MuMuTestUp、IntTestGen、MockBench及公开mutation-shield benchmark的重叠。候选不是“首次防止断言削弱/引入mutation”，而是待验证的“失败测试中部分有效检查及其冻结区分见证保持”。目前novelty_established=false；真实频度、支持率、相对简单冻结规则的额外价值均未验证。既有RQ与权威研究计划不变。
