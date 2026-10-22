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

## 10 月 22 日核验结果

Git 完整克隆在新环境超时，改为由 GitHub API 解析完整提交，再下载官方归档。较大归档可从本地下载并上传到缓存；`scripts/fetch_kcf_project_archives.py` 核对缓存根目录中的提交号、记录归档 SHA-256、拒绝覆盖未验证目录。归档获取的源码不含 `.git`，版本依据 `.kcf-source.json` 和结果目录的 `source_manifest.json`，不能伪称 Git checkout。

当前六项目源码位于 `/root/autodl-tmp/kcf-projects-20261022`，原清单兼容软链接 `/root/maco-aligned-projects` 指向该目录。原不完整目录保留。

41 个目标文件/方法均找到，六项目构建全部通过。JDom2 的 Java 17/source 1.6 组合实测不兼容，本轮以 Java 8 显式覆盖后成功；原始项目清单未改。复跑构建命令如下，前提是已完成归档下载并核验源码：

```bash
python scripts/verify_kcf_environment.py --method-list experiments/method_lists/kcf_utg_rq1_methods_v1.json --project-manifest experiments/maco_aligned_41_projects.json --projects-root /root/autodl-tmp/kcf-projects-20261022 --output-dir experiments/runs/rebuild_20261022/build_final --build --java-home /usr/lib/jvm/java-8-openjdk-amd64 --workers 3 --timeout 420 --maven-settings config/maven.kcf-settings.xml
```

新运行使用新输出目录，避免覆盖证据。核验报告及日志见 `results/rebuild_20261022/`。TreeList 同名外层/内层方法匹配问题需要在新效果评估前解决；目前未运行新模型生成，也未形成新版 RQ1/RQ2 结论。
