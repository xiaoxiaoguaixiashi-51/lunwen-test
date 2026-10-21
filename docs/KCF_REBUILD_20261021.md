# 新实例重跑记录

本次从全新 Ubuntu 22.04 实例开始部署，执行最终路线的六项目、41 个方法 RQ1/RQ2。旧云端实例已释放，保存在本地的历史摘要和归档仅作为历史证据。

## 路径与依赖

- 数据盘：`/root/autodl-tmp`（100GB）。
- 项目代码：`/root/autodl-tmp/lunwen-test`，通过 `/root/lunwen-test` 访问。
- 六项目源码：`/root/autodl-tmp/maco-aligned-projects`，通过 `/root/maco-aligned-projects` 兼容固定清单中的路径。
- 安装 Java 8/17、Python 3、Maven、Ant、tmux；每个项目需实际构建核验。
- 模型 API 尚需单独配置；示例 YAML 的 localhost 和模型名称是占位配置，不代表已运行模型。

## GitHub 与结果备份

代码和可公开证据先发布到 `codex/kcf-rebuild-20261021` 分支。各批次完成后，先下载到本地并校验哈希，再发布汇总表、目标方法状态、脱敏运行参数和证据索引。原始生成 Java、编译/运行日志、JaCoCo XML 也应归档保留；体积超出普通 Git 文件适用范围的归档通过 GitHub Release 附件发布，仓库索引记录位置及 SHA-256。

不上传私钥、API key、密码、含凭据的配置或原始认证输出。云端实例不是唯一备份位置。尚未上传的结果不得写成已同步。

## 顺序

1. 安装系统依赖，上传固定提交代码，在云端执行单测。
2. 检出六项目并记录解析后的完整提交 SHA，核对全部目标方法源码。
3. 逐项目构建并配置 EvoSuite、JUnit、JaCoCo。
4. 配置模型 API，测量小样本时间/成本，核验 RQ2 两阶段开关。
5. 冻结模型和预算，运行 RQ1/RQ2；每批保存原始材料、下载备份并同步 GitHub。

本记录是部署计划，不是完成报告；以实际安装日志和运行产物为准。
