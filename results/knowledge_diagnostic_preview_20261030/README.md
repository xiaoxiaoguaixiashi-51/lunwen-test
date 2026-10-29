# 四处理离线请求预览

2026-10-30。48 个计划单元已生成：4 个开发案例 × N/F/L/T × 3 次重复。API 请求为零；不是实验结果，不报告编译率、运行率或覆盖收益。

## 已完成

- 核验冻结归档与知识库 SHA-256，并重放核对原 L 排名的 ID/分数。
- 确定性生成固定经验选择、L 选择、T（binary-TF / smoothed-IDF / cosine）选择及分块请求顺序。
- 渲染与当前修复模板一致的 system/user 消息；知识内容不展示 retrieval_score。
- 记录原测试、原日志、保存的源码上下文、查询与完整消息的哈希；同 case/repeat 的四处理共同输入一致。
- 公开 `manifest.json` 仅含索引、哈希、选择和字节数；完整预览在本目录 `previews/`，已通过本目录 .gitignore 排除，不上传原文提示。模板内的历史 Ours Full 名称保留为复用实现，不是论文新增主张。

## 尚未满足的发送条件

所有单元均为 `executable: false`。历史 source_context.json 内的 context 仅用于预览，尚未与本次云端源树重新比对；模型有效配置、Java/JaCoCo 工具与独立执行路径也尚未在本工具验证。工具不读取密钥、不初始化 LLMClient，也不下载 tokenizer。

预算状态全部为 `unmeasured_no_verified_tokenizer`。消息 JSON 的 UTF-8 字节数介于 14561–42999，**字节数不是 token 数，也不是服务计费值**。不能据此断言全部满足 12000 输入 token 上限或估计准确费用；应先确定兼容模型的本地 tokenizer 和消息封装计数方式，再执行逐请求门禁。

不同排序确实产生不同知识 ID，但这仅验证处理有差异，不证明 T 或 L 更相关/有效。相同提示重复三次只代表计划中的独立请求，不意味着已经执行或服务端随机种子已固定。

## 验证

新增四项测试通过：零相似度/并列处理、固定选择不受输入顺序影响、真实归档 48 单元的共同输入/无分数提示/禁止 socket 网络、变更输入拒绝。完整离线回归共 157 项，156 通过，1 项因本地未设置真实 Java/JaCoCo 工具环境而跳过；没有将跳过项写成通过。

重建预览命令（必须使用新的输出目录；不会覆盖本批结果）：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_knowledge_diagnostic.py --archive results/seed_failure_repair_20261022/seed_failure_repair_20261022.tgz --knowledge experiments/knowledge/dependency_construction_knowledge.jsonl --output-dir <new-preview-directory>
```

实验处理/预算依据：`docs/KNOWLEDGE_SELECTION_DIAGNOSTIC_20261030.md`。下一步只需补云端输入复核及可信 token 计数，不应重新做环境重建或修改既定 RQ1/RQ2。正式付费执行仍需冻结有效配置与执行器，不能将预览文件直接当作获准请求队列。
