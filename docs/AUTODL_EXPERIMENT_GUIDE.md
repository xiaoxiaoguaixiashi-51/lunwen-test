# AutoDL 云端实验启动指南

本指南用于把正式实验迁移到 AutoDL。当前项目的默认策略是：

- AutoDL 只作为实验执行服务器。
- LLM 使用外部 OpenAI 兼容 API。
- 不在 AutoDL 本地部署大模型。
- 先跑 smoke，再跑 RQ1 pilot，最后扩展到 RQ1 full。

## 1. 创建实例

推荐配置：

- 系统：Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS
- CPU/内存：优先 8 核 CPU、16GB 内存
- 磁盘：建议 200GB
- GPU：不是关键指标；如果 AutoDL 没有纯 CPU 或低配实例，选择最低成本 GPU 实例即可

不要为了显卡额外增加预算，除非后续决定在服务器本地部署大模型。

## 2. 登录服务器

在 AutoDL 控制台复制 SSH 登录命令，例如：

```bash
ssh -p <port> root@<host>
```

建议进入服务器后先开 `tmux`，避免 SSH 断开导致实验中断：

```bash
tmux new -s setup
```

## 3. 获取项目代码

当前计划使用 Git 拉取项目：

```bash
cd /root
git clone <your_repo_url> lunwen-test
cd lunwen-test
```

注意：本地目录目前不是 git 仓库。正式开始前，需要先把本地项目推到远程仓库，或者确认已有可 `git clone` 的仓库地址。

## 4. 安装云端环境

项目提供 AutoDL 初始化脚本：

```bash
bash scripts/autodl_setup.sh
```

这个脚本会安装：

- Git
- Python venv/pip
- OpenJDK 17
- Maven
- unzip/curl/tmux
- Python requirements

如果脚本因权限或网络失败，可以手动执行：

```bash
apt update
apt install -y git python3 python3-venv python3-pip openjdk-17-jdk maven unzip curl tmux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. 配置 LLM API

不要把 API key 写入公开仓库。推荐在服务器 shell 中临时设置环境变量：

```bash
export LLM_BASE_URL="<OpenAI-compatible API base_url>"
export LLM_API_KEY="<api_key>"
export LLM_MODEL="<model_name>"
```

然后生成 `config/config.yaml`：

```bash
bash scripts/autodl_setup.sh --write-config
```

也可以手动复制模板：

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

## 6. Smoke 验收

在项目根目录执行：

```bash
bash scripts/autodl_smoke.sh
```

脚本会依次检查：

1. `python --version`
2. `java -version`
3. `mvn -version`
4. `python -m unittest discover tests`
5. `examples/java-demo` 下的 `mvn test`
6. 单方法 pipeline
7. batch runner smoke

成功后应能看到：

- `experiments/smoke/`
- `experiments/runs/smoke/summary.json`
- 每个方法目录下的 `status.json`

## 7. RQ1 pilot

先用 5-10 个方法跑小规模 pilot。方法列表模板在：

```bash
experiments/method_lists/rq1_pilot.example.json
```

先计算 DCCI，并筛选 DCCI >= 1 的方法：

```bash
source .venv/bin/activate
python -m src.metrics.dcci \
  --input experiments/method_lists/rq1_pilot.example.json \
  --output experiments/method_lists/rq1_pilot.scored.json

python scripts/build_method_list.py \
  --input experiments/method_lists/rq1_pilot.scored.json \
  --output experiments/method_lists/rq1_pilot.json \
  --min-dcci 1.0 \
  --limit 10 \
  --runner-only
```

运行命令：

```bash
source .venv/bin/activate
python -m src.core.batch_runner \
  --methods experiments/method_lists/rq1_pilot.json \
  --output experiments/runs/rq1_pilot
```

pilot 目标：

- 确认批量运行不断点。
- 确认每个方法独立输出。
- 统计失败原因：配置错误、编译错误、运行错误、LLM 调用错误。
- 再决定是否扩展到 RQ1 full。

## 8. RQ1 full

正式方法列表建议命名为：

```bash
experiments/method_lists/rq1_full.json
```

长任务使用 `tmux`：

```bash
tmux new -s rq1
source .venv/bin/activate
python -m src.core.batch_runner \
  --methods experiments/method_lists/rq1_full.json \
  --output experiments/runs/rq1_full
```

如果 SSH 断开，重新连接后：

```bash
tmux attach -t rq1
```

## 8.1 结果汇总表

批量实验完成后，先把 `summary.json` 和每个方法目录下的 `status.json`、`*_report.json` 汇总成表格：

```bash
source .venv/bin/activate
python scripts/summarize_run.py \
  --run-dir experiments/runs/rq1_pilot_v2 \
  --csv experiments/runs/rq1_pilot_v2/summary_table.csv \
  --markdown experiments/runs/rq1_pilot_v2/summary_table.md
```

真实 pilot 建议使用同样方式生成：

```bash
python scripts/summarize_run.py \
  --run-dir experiments/runs/rq1_pilot_real \
  --csv experiments/runs/rq1_pilot_real/summary_table.csv \
  --markdown experiments/runs/rq1_pilot_real/summary_table.md
```

这张表用于导师展示和失败原因复盘；`experiments/runs/` 仍然不要提交到 Git。

## 8.2 从 demo pilot_v2 过渡到真实 Defects4J pilot

真实 RQ1 pilot 的最小闭环建议如下：

1. 在 AutoDL 上 checkout 或复制 5-10 个 Defects4J 真实项目/bug 版本。
2. 按 `experiments/method_lists/rq1_pilot_real.template.json` 的字段格式记录候选方法。
3. 运行 DCCI 评分：

```bash
python -m src.metrics.dcci \
  --input experiments/method_lists/rq1_candidates_real.json \
  --output experiments/method_lists/rq1_candidates_real.scored.json
```

4. 筛选真实 pilot 方法：

```bash
python scripts/build_method_list.py \
  --input experiments/method_lists/rq1_candidates_real.scored.json \
  --output experiments/method_lists/rq1_pilot_real.json \
  --min-dcci 1.0 \
  --limit 10 \
  --runner-only
```

5. 执行真实 pilot：

```bash
python -m src.core.batch_runner \
  --methods experiments/method_lists/rq1_pilot_real.json \
  --output experiments/runs/rq1_pilot_real
```

## 9. 实验保存规则

每次正式实验至少保存：

- 运行命令
- 脱敏后的 `config.yaml`
- 方法列表 JSON
- 每个方法的生成测试代码
- 每个方法的 report/status JSON
- 编译和运行日志
- 覆盖率报告
- mutation score 报告

不要提交：

- `config/config.yaml`
- `.venv/`
- `experiments/runs/`
- API key

## 10. 与第一阶段计划的对应关系

当前第一优先级不是直接跑全量 RQ1，而是按下面顺序推进：

1. AutoDL 环境验收。
2. `smoke.json` 跑通。
3. `rq1_pilot.example.json` 扩成 5-10 个真实方法。
4. 跑 RQ1 pilot。
5. 扩展为 `rq1_full.json`。
6. 跑 EvoSuite、RAG + LLM、Ours Full 的正式 RQ1。
7. MACO/ChatUniTest 使用 published comparison，不完整复刻。
