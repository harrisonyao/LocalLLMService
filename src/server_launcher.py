import json
import logging
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger("vllm_server.launcher")
ENV_FILE = Path(__file__).with_name(".env")
LEGACY_ENV_MAP = {
    "VLLM_MODEL": "LLM_MODEL",
    "VLLM_SERVED_MODEL_NAME": "LLM_SERVED_MODEL_NAME",
    "VLLM_HOST": "LLM_HOST",
    "VLLM_PORT": "LLM_PORT",
    "VLLM_DTYPE": "LLM_DTYPE",
    "VLLM_GPU_MEMORY_UTILIZATION": "LLM_GPU_MEMORY_UTILIZATION",
    "VLLM_MAX_MODEL_LEN": "LLM_MAX_MODEL_LEN",
    "VLLM_MAX_NUM_SEQS": "LLM_MAX_NUM_SEQS",
    "VLLM_MAX_NUM_BATCHED_TOKENS": "LLM_MAX_NUM_BATCHED_TOKENS",
    "VLLM_TENSOR_PARALLEL_SIZE": "LLM_TENSOR_PARALLEL_SIZE",
    "VLLM_ENABLE_REQUEST_ID_HEADERS": "LLM_ENABLE_REQUEST_ID_HEADERS",
    "VLLM_DISABLE_FASTAPI_DOCS": "LLM_DISABLE_FASTAPI_DOCS",
    "VLLM_DISABLE_UVICORN_ACCESS_LOG": "LLM_DISABLE_UVICORN_ACCESS_LOG",
    "VLLM_TRUST_REMOTE_CODE": "LLM_TRUST_REMOTE_CODE",
    "VLLM_ENABLE_LOG_REQUESTS": "LLM_ENABLE_LOG_REQUESTS",
    "VLLM_API_KEYS": "LLM_API_KEYS",
    "VLLM_EXTRA_ARGS": "LLM_EXTRA_ARGS",
    "VLLM_UVICORN_LOG_LEVEL": "LLM_UVICORN_LOG_LEVEL",
    "VLLM_ROOT_PATH": "LLM_ROOT_PATH",
    "VLLM_ALLOWED_ORIGINS": "LLM_ALLOWED_ORIGINS",
    "VLLM_ALLOWED_METHODS": "LLM_ALLOWED_METHODS",
    "VLLM_ALLOWED_HEADERS": "LLM_ALLOWED_HEADERS",
    "VLLM_SSL_KEYFILE": "LLM_SSL_KEYFILE",
    "VLLM_SSL_CERTFILE": "LLM_SSL_CERTFILE",
    "VLLM_SSL_CA_CERTS": "LLM_SSL_CA_CERTS",
    "VLLM_H11_MAX_HEADER_COUNT": "LLM_H11_MAX_HEADER_COUNT",
}


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip())


load_env_file(ENV_FILE)


def normalize_legacy_env_vars() -> None:
    for legacy_name, new_name in LEGACY_ENV_MAP.items():
        legacy_value = os.environ.get(legacy_name)
        if legacy_value is not None and new_name not in os.environ:
            os.environ[new_name] = legacy_value
        os.environ.pop(legacy_name, None)


normalize_legacy_env_vars()


import uvloop
from vllm.entrypoints.openai.api_server import run_server
from vllm.entrypoints.openai.cli_args import (
    make_arg_parser,
    validate_parsed_serve_args,
)
from vllm.entrypoints.utils import cli_env_setup
from vllm.utils.argparse_utils import FlexibleArgumentParser


@dataclass
class ServiceSettings:
    model: str = field(init=False)
    served_model_name: str = field(init=False)
    host: str = field(init=False)
    port: int = field(init=False)
    dtype: str = field(init=False)
    gpu_memory_utilization: float = field(init=False)
    max_model_len: str | None = field(init=False)
    max_num_seqs: str | None = field(init=False)
    max_num_batched_tokens: str | None = field(init=False)
    tensor_parallel_size: int = field(init=False)
    api_keys: list[str] = field(init=False)
    disable_uvicorn_access_log: bool = field(init=False)
    enable_request_id_headers: bool = field(init=False)
    disable_fastapi_docs: bool = field(init=False)
    trust_remote_code: bool = field(init=False)
    enable_log_requests: bool = field(init=False)
    uvicorn_log_level: str = field(init=False)
    root_path: str | None = field(init=False)
    allowed_origins: list[str] = field(init=False)
    allowed_methods: list[str] = field(init=False)
    allowed_headers: list[str] = field(init=False)
    ssl_keyfile: str | None = field(init=False)
    ssl_certfile: str | None = field(init=False)
    ssl_ca_certs: str | None = field(init=False)
    h11_max_header_count: int = field(init=False)
    extra_args: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.model = os.getenv("LLM_MODEL", "Qwen/Qwen3-Coder-30B-A3B-Instruct")
        self.served_model_name = os.getenv("LLM_SERVED_MODEL_NAME", "qwen3-coder")
        self.host = os.getenv("LLM_HOST", "0.0.0.0")
        self.port = int(os.getenv("LLM_PORT", "8000"))
        self.dtype = os.getenv("LLM_DTYPE", "auto")
        self.gpu_memory_utilization = float(
            os.getenv("LLM_GPU_MEMORY_UTILIZATION", "0.92")
        )
        self.max_model_len = os.getenv("LLM_MAX_MODEL_LEN")
        self.max_num_seqs = os.getenv("LLM_MAX_NUM_SEQS", "16")
        self.max_num_batched_tokens = os.getenv(
            "LLM_MAX_NUM_BATCHED_TOKENS", "16384"
        )
        self.tensor_parallel_size = int(os.getenv("LLM_TENSOR_PARALLEL_SIZE", "1"))
        self.api_keys = env_list("LLM_API_KEYS")
        self.disable_uvicorn_access_log = env_flag(
            "LLM_DISABLE_UVICORN_ACCESS_LOG", True
        )
        self.enable_request_id_headers = env_flag(
            "LLM_ENABLE_REQUEST_ID_HEADERS", True
        )
        self.disable_fastapi_docs = env_flag("LLM_DISABLE_FASTAPI_DOCS", True)
        self.trust_remote_code = env_flag("LLM_TRUST_REMOTE_CODE", False)
        self.enable_log_requests = env_flag("LLM_ENABLE_LOG_REQUESTS", False)
        self.uvicorn_log_level = os.getenv("LLM_UVICORN_LOG_LEVEL", "info")
        self.root_path = os.getenv("LLM_ROOT_PATH")
        self.allowed_origins = env_list("LLM_ALLOWED_ORIGINS") or ["*"]
        self.allowed_methods = env_list("LLM_ALLOWED_METHODS") or ["*"]
        self.allowed_headers = env_list("LLM_ALLOWED_HEADERS") or ["*"]
        self.ssl_keyfile = os.getenv("LLM_SSL_KEYFILE")
        self.ssl_certfile = os.getenv("LLM_SSL_CERTFILE")
        self.ssl_ca_certs = os.getenv("LLM_SSL_CA_CERTS")
        self.h11_max_header_count = int(os.getenv("LLM_H11_MAX_HEADER_COUNT", "256"))
        self.extra_args = shlex.split(os.getenv("LLM_EXTRA_ARGS", ""))

    def to_cli_args(self) -> list[str]:
        args = [
            "--model",
            self.model,
            "--served-model-name",
            self.served_model_name,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--dtype",
            self.dtype,
            "--gpu-memory-utilization",
            str(self.gpu_memory_utilization),
            "--tensor-parallel-size",
            str(self.tensor_parallel_size),
            "--uvicorn-log-level",
            self.uvicorn_log_level,
            "--allowed-origins",
            json.dumps(self.allowed_origins),
            "--allowed-methods",
            json.dumps(self.allowed_methods),
            "--allowed-headers",
            json.dumps(self.allowed_headers),
            "--disable-access-log-for-endpoints",
            "/health,/metrics",
            "--middleware",
            "audit_middleware.RequestAuditMiddleware",
            "--h11-max-header-count",
            str(self.h11_max_header_count),
        ]

        if self.max_model_len:
            args.extend(["--max-model-len", self.max_model_len])
        if self.max_num_seqs:
            args.extend(["--max-num-seqs", self.max_num_seqs])
        if self.max_num_batched_tokens:
            args.extend(["--max-num-batched-tokens", self.max_num_batched_tokens])
        if self.disable_uvicorn_access_log:
            args.append("--disable-uvicorn-access-log")
        if self.enable_request_id_headers:
            args.append("--enable-request-id-headers")
        if self.disable_fastapi_docs:
            args.append("--disable-fastapi-docs")
        if self.trust_remote_code:
            args.append("--trust-remote-code")
        if self.enable_log_requests:
            args.append("--enable-log-requests")
        if self.root_path:
            args.extend(["--root-path", self.root_path])
        if self.ssl_keyfile:
            args.extend(["--ssl-keyfile", self.ssl_keyfile])
        if self.ssl_certfile:
            args.extend(["--ssl-certfile", self.ssl_certfile])
        if self.ssl_ca_certs:
            args.extend(["--ssl-ca-certs", self.ssl_ca_certs])
        for api_key in self.api_keys:
            args.extend(["--api-key", api_key])
        args.extend(self.extra_args)
        return args


def parse_wrapper_args(argv: list[str]) -> tuple[bool, bool, list[str]]:
    print_config = False
    check_config = False
    passthrough = []

    for arg in argv:
        if arg == "--print-config":
            print_config = True
        elif arg == "--check-config":
            check_config = True
        else:
            passthrough.append(arg)

    return print_config, check_config, passthrough


def build_parser() -> FlexibleArgumentParser:
    return make_arg_parser(
        FlexibleArgumentParser(
            description="Production wrapper around the official vLLM OpenAI server."
        )
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    cli_env_setup()
    configure_logging()

    print_config, check_config, passthrough = parse_wrapper_args(sys.argv[1:])
    settings = ServiceSettings()
    cli_args = settings.to_cli_args() + passthrough

    parser = build_parser()
    args = parser.parse_args(cli_args)
    validate_parsed_serve_args(args)

    summary = {
        "model": args.model,
        "served_model_name": args.served_model_name,
        "host": args.host,
        "port": args.port,
        "dtype": args.dtype,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "max_model_len": args.max_model_len,
        "max_num_seqs": args.max_num_seqs,
        "max_num_batched_tokens": args.max_num_batched_tokens,
        "tensor_parallel_size": args.tensor_parallel_size,
        "middleware": args.middleware,
        "api_key_enabled": bool(args.api_key),
    }

    if print_config or check_config:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    if check_config:
        return

    LOGGER.info("Starting vLLM server with summary=%s", json.dumps(summary))
    uvloop.run(run_server(args))


if __name__ == "__main__":
    main()
