# vLLM Server Production Skeleton

这个仓库现在提供一套适合裸机 GPU 服务器部署的基础骨架：

- 通过官方 `vllm.entrypoints.openai.api_server.run_server(args)` 启动，而不是手工拼 FastAPI app。
- 通过环境变量管理模型、显存、水位、鉴权和模型别名。
- 默认启用请求审计中间件，只记录请求次数和元数据，不落 prompt 明文。
- 客户端默认走非流式调用，保留单独的流式方法。

## 目录

- `server_launcher.py`: vLLM 官方启动入口包装器。
- `audit_middleware.py`: 结构化请求审计日志。
- `unified_client.py`: OpenAI 兼容客户端示例，默认非流式。
- `.env.example`: 通用环境变量模板。
- `deploy/env.5090.example`: 5090 单卡参考配置。
- `deploy/env.4090.example`: 4090 兼容骨架参考配置。
- `deploy/systemd/vllm-server.service`: 裸机 systemd 服务模板。

## 快速开始

1. 创建 Python 环境并安装依赖：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

2. 准备配置：

```bash
cp .env.example .env
```

如果目标是 5090，可以先参考 `deploy/env.5090.example`。

3. 在上线前先做配置检查：

```bash
set -a && source .env && set +a
python server_launcher.py --check-config
python server_launcher.py --print-config
```

4. 启动服务：

```bash
set -a && source .env && set +a
python server_launcher.py
```

## 关键接口

- `GET /health`: vLLM 引擎健康检查，不走 `/v1` 鉴权。
- `GET /metrics`: Prometheus 指标。
- `GET /v1/models`: 查看当前对外暴露的模型名。
- `POST /v1/chat/completions`: OpenAI 兼容聊天接口。

## 鉴权

如果设置 `VLLM_API_KEYS=key1,key2`，vLLM 会要求 `/v1/*` 请求携带 `Authorization: Bearer <key>`。

## 日志

请求审计日志输出到 stdout/journald，格式为单行 JSON，例如：

```json
{"client_ip":"10.0.0.8","content_length":"812","duration_ms":1532.44,"event":"llm_request","method":"POST","path":"/v1/chat/completions","request_id":"a1b2c3","status_code":200}
```

默认只记录元数据，不记录 prompt。这样可以满足“知道有多少请求、每个请求耗时如何”的内部审计诉求。

## 4090 与 5090 兼容建议

- 代码骨架本身同时兼容 4090 和 5090，差异主要体现在 `.env` 参数。
- `Qwen/Qwen3-Coder-30B-A3B-Instruct` 更适合 5090 这类显存更充裕的卡。
- 4090 24GB 场景请优先选择量化版模型、减小 `VLLM_MAX_MODEL_LEN`，并降低并发参数。
- 不要复用 macOS 本地环境到 Linux GPU 主机；需要在目标机器重新安装 CUDA 对应的 vLLM/PyTorch 环境。

## systemd 部署

把仓库放到目标机，例如 `/opt/vllm-server`，并准备：

```bash
cp deploy/systemd/vllm-server.service /etc/systemd/system/vllm-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now vllm-server
sudo systemctl status vllm-server
```

## 客户端示例

```python
from unified_client import QwenCoderClient

client = QwenCoderClient()
result = client.optimize_code("请优化这段 Python 代码")
print(result)
```

## 建议的上线前检查

- `python server_launcher.py --check-config`
- `curl http://127.0.0.1:8000/health`
- `curl http://127.0.0.1:8000/v1/models`
- 使用真实请求打一次 `/v1/chat/completions`
- 观察 `journalctl -u vllm-server -f` 中的单行 JSON 审计日志
