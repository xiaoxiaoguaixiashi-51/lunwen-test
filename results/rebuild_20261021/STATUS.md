# 全新云端环境部署状态

对应代码提交：`9a0e11a40cc392fc83c08272257344dc4dfeb6ea`。

- 已完成 SSH 认证、代码上传，代码位于 100GB 数据盘。
- 已安装 Java 8、Java 17、Maven 3.6.3、Ant 1.10.12、Python 3.10 虚拟环境及项目 Python 依赖；锁定列表见本目录 `requirements.lock.txt`。
- 本地 113 项单测通过。云端测试触发 Maven 依赖下载，尚未完成，不能报告为云端验证通过。
- GitHub 和 Maven 的 HTTPS 探测成功；首个完整项目 Git clone 超时，六项目检出尚未完成。
- 模型 API 尚未配置，尚未启动付费模型调用或正式 RQ1/RQ2。

本目录记录环境重建进度，不包含正式覆盖率结果。后续每批正式运行保存生成 Java、编译/运行日志、覆盖 XML 和脱敏参数；下载校验后发布证据索引与汇总。大型原始归档使用 GitHub Release 附件并记录 SHA-256。
