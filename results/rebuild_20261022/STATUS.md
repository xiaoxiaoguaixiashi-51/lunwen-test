# 返工部署：固定源码与构建核验

本次工作继续已完成 RQ1/RQ2 的返工准备，不生成新的覆盖率效果结论。

- Git 完整克隆超时后改用官方 GitHub 源码归档；六项目均已取得源码，`source_manifest.json` 记录解析后的完整提交和归档 SHA-256。
- CSV、JDom2 的大归档经本地下载后传入云端缓存；缓存根目录名需匹配解析出的提交号。没有更换目标项目版本或方法清单。
- 已找到 41/41 个目标文件和方法，目标文件哈希及匹配范围见 `target_verification.json`。其中一个方法名对应多个范围，保留该历史歧义，不自动合并成已确认的唯一签名。
- 原不完整克隆目录保留。`/root/maco-aligned-projects` 软链接已指向完整源码目录 `/root/autodl-tmp/kcf-projects-20261022`。
- 原项目清单中 JDom2 的 Java 17 配置与 `source/target 1.6` 不兼容，实测失败；明确覆盖为 Java 8 后构建成功。保留原清单及失败/重试记录。
- 整组六项目使用 Java 8 验证完成：Commons-CLI、Commons-CSV、Commons-codec、Commons-collections4、JDom2、Windward 均构建成功，见 `build_summary.json` 及 `build_logs/`。Maven 项目使用显式镜像设置。
- 新增归档获取和构建核验脚本；本地 115 项单测通过。尚未启动模型生成。

Maven 设置只由本次命令的 `-s config/maven.kcf-settings.xml` 指定，不改全局设置。每项目构建日志记录命令和实际 JDK。部署报告与正式实验结果分开，旧实验数据保持原样。

## 新发现的评估口径问题

`TreeList.addAll` 的旧名称匹配器同时返回外层公开方法（959–969 行）和内层 `AVLNode` 的私有同名方法（180–273 行）。这不是已确认的普通重载；当前清单指定的类为外层 `TreeList`。

旧 JSON 已标记 `ambiguous_methods: 1`。新统计前应明确方法所属类和参数签名，再评估分母影响；此处不自动修改旧汇总，也不将多个范围当作无歧义匹配。修正后的口径需要在各比较方法间一致应用，不能直接沿用旧分母 1100/802 作为新运行的既定分母。

## 本地备份

六项目完整提交清单、目标核验报告、成功构建汇总和逐项目日志随本目录同步 GitHub。包含失败探测和重试日志的完整环境证据包为本目录 `environment_evidence.tgz`，另有外层 `outputs/rebuild_20261022_environment_evidence.tgz` 本地副本；它不包含模型凭据或正式生成结果。归档 SHA-256：`68ed79ecdb4da7dd21b85153f25d7985e6bbf1316ddd0d892dcb41339dffa1c6`。
