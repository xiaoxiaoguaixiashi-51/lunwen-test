# 云端实验新手指南

这份指南面向第一次使用云服务器的实验流程。当前项目建议在云端只运行 Python、Java、Maven、EvoSuite、PIT 和批量脚本，LLM 使用 OpenAI 兼容 API，不在服务器本地部署大模型。

如果使用 AutoDL，优先阅读更具体的启动指南：[`docs/AUTODL_EXPERIMENT_GUIDE.md`](AUTODL_EXPERIMENT_GUIDE.md)。

## 1. 服务器建议

- 系统：Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS
- 最低配置：4 核 CPU、8GB 内存、100GB 磁盘
- 更稳妥配置：8 核 CPU、16GB 内存、200GB 磁盘
- GPU：不需要，除非后续决定自己部署大模型

## 2. 第一次登录前需要准备

等开始云端部署时，先确认这四项信息：

1. 云平台名称
2. 服务器公网 IP
3. 登录方式：密码或 SSH 密钥
4. 系统版本：Ubuntu 22.04/24.04 或其他

## 3. 云端环境安装顺序

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip openjdk-17-jdk maven unzip curl
```

进入项目目录后创建 Python 环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

AutoDL 上可以直接执行：

```bash
bash scripts/autodl_setup.sh
```

## 4. Smoke Test 顺序

先验证 Java 示例项目：

```bash
cd examples/java-demo
mvn test
```

再回到项目根目录，验证 Python 离线测试：

```bash
python -m unittest discover tests
```

最后跑一个方法的 pipeline：

```bash
python -m src.core.pipeline \
  --target examples/java-demo/src/main/java/com/example/service/UserService.java \
  --method updateUserEmail \
  --output experiments/smoke
```

## 5. 批量实验入口

方法列表使用 JSON 数组，每个条目包含 `id`、`target`、`method`。

```bash
python -m src.core.batch_runner \
  --methods examples/method_lists/smoke.json \
  --output experiments/runs
```

AutoDL 上可以直接执行完整 smoke 验收：

```bash
bash scripts/autodl_smoke.sh
```

批量运行会为每个方法创建独立目录，并写入 `status.json`。默认开启断点续跑，已经完成的条目不会重复运行。

## 6. 实验结果保存规则

每次正式实验都保留：

- 使用的 config
- 每个方法的生成测试代码
- 每个方法的 report/status JSON
- 编译和运行日志
- 覆盖率报告
- mutation score 报告

这些文件后续用于论文表格、消融实验和复现实验。
