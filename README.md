# LocalLLMService

适用于内部代码模型服务的 vLLM 生产骨架，当前默认目标模型为 `Qwen/Qwen3-Coder-30B-A3B-Instruct`。

## 目录结构

代码和环境模板统一放在 `src/`：

- `src/server_launcher.py`: 读取环境变量并调用官方 `run_server(args)`。
- `src/audit_middleware.py`: 输出单行 JSON 审计日志。
- `src/unified_client.py`: OpenAI 兼容客户端示例。
- `src/.env.example`: 通用环境变量模板。
- `src/env.5090.compose.example`: 5090 的完整 Compose 模板。
- `src/env.5090.example`: 5090 的参数覆盖模板。
- `src/env.4090.example`: 4090 兼容参数模板。

非代码与部署文件保留在根目录或 `deploy/`：

- `Dockerfile`
- `docker-compose.yml`
- `deploy/scripts/bootstrap_5090.sh`
- `deploy/systemd/vllm-server.service`

## 运行方式

### Docker Compose

1. 准备环境变量：

```bash
cp src/env.5090.compose.example src/.env
```

2. 校验配置：

```bash
docker compose --env-file src/.env config
```

3. 构建并启动：

```bash
docker compose --env-file src/.env up -d --build
```

4. 检查健康状态：

```bash
docker compose --env-file src/.env ps
curl http://127.0.0.1:8000/health
```

### 本地 Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp src/.env.example src/.env
set -a && source src/.env && set +a
python src/server_launcher.py --check-config
python src/server_launcher.py
```

### 5090 一键部署

目标机建议为 Ubuntu 22.04/24.04，已安装 NVIDIA 驱动。

```bash
curl -fsSL https://raw.githubusercontent.com/harrisonyao/LocalLLMService/main/deploy/scripts/bootstrap_5090.sh | sudo bash
```

脚本默认会：

- 安装 Docker Engine 和 Compose Plugin。
- 安装 NVIDIA Container Toolkit。
- 拉取或更新 `LocalLLMService` 仓库到 `/opt/LocalLLMService`。
- 从 `src/env.5090.compose.example` 生成 `src/.env`。
- 用 `docker compose --env-file src/.env up -d --build` 拉起服务。

可通过环境变量覆盖：

```bash
sudo REPO_URL=https://github.com/harrisonyao/LocalLLMService.git APP_DIR=/opt/LocalLLMService bash deploy/scripts/bootstrap_5090.sh
```

## 关键接口

- `GET /health`: 引擎健康检查。
- `GET /metrics`: Prometheus 指标。
- `GET /v1/models`: 当前对外暴露模型。
- `POST /v1/chat/completions`: OpenAI 兼容聊天接口。

## 日志

请求审计日志输出到 stdout、docker logs 或 journald，格式为单行 JSON：

```json
{"client_ip":"10.0.0.8","content_length":"812","duration_ms":1532.44,"event":"llm_request","method":"POST","path":"/v1/chat/completions","request_id":"a1b2c3","status_code":200}
```

默认只记元数据，不记 prompt 明文。

## 鉴权

如果设置：

```bash
VLLM_API_KEYS=key1,key2
```

则 `/v1/*` 请求需要携带：

```text
Authorization: Bearer <key>
```

`/health` 和 `/metrics` 不受 `/v1` 鉴权影响。

## 4090 与 5090

- 代码骨架同时兼容 4090 和 5090。
- `Qwen/Qwen3-Coder-30B-A3B-Instruct` 更适合 5090。
- 4090 24GB 场景请优先替换为量化版模型或更小模型，并降低 `VLLM_MAX_MODEL_LEN`、`VLLM_MAX_NUM_SEQS`。
- 不要把 macOS 本地环境直接迁移到 Linux GPU 机；请在目标机重新构建镜像或重新安装依赖。

## 客户端示例

```python
from src.unified_client import QwenCoderClient

client = QwenCoderClient()
result = client.optimize_code("请优化这段 Python 代码")
print(result)
```

## 裸机 systemd

如果你不走 Docker，可以使用 `deploy/systemd/vllm-server.service`，它会从 `src/.env` 读取环境变量，并启动 `src/server_launcher.py`。

## 上线前检查

- `docker compose --env-file src/.env config`
- `docker compose --env-file src/.env ps`
- `curl http://127.0.0.1:8000/health`
- `curl http://127.0.0.1:8000/v1/models`
- 用真实请求打一次 `/v1/chat/completions`
- `docker logs -f local-llm-service`
