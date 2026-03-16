import json
import logging
import os
import shlex
import sys
from dataclasses import dataclass

import uvloop
from vllm.entrypoints.openai.api_server import run_server
from vllm.entrypoints.openai.cli_args import (
    make_arg_parser,
    validate_parsed_serve_args,
)
from vllm.entrypoints.utils import cli_env_setup
from vllm.utils.argparse_utils import FlexibleArgumentParser


LOGGER = logging.getLogger("vllm_server.launcher")


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class ServiceSettings:
    model: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-Coder-30B-A3B-Instruct")
    served_model_name: str = os.getenv("VLLM_SERVED_MODEL_NAME", "qwen3-coder")
    host: str = os.getenv("VLLM_HOST", "0.0.0.0")
    port: int = int(os.getenv("VLLM_PORT", "8000"))
    dtype: str = os.getenv("VLLM_DTYPE", "auto")
    gpu_memory_utilization: float = float(
        os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.92")
    )
    max_model_len: str | None = os.getenv("VLLM_MAX_MODEL_LEN")
    max_num_seqs: str | None = os.getenv("VLLM_MAX_NUM_SEQS", "16")
    max_num_batched_tokens: str | None = os.getenv(
        "VLLM_MAX_NUM_BATCHED_TOKENS", "16384"
    )
    tensor_parallel_size: int = int(os.getenv("VLLM_TENSOR_PARALLEL_SIZE", "1"))
    api_keys: list[str] = None
    disable_uvicorn_access_log: bool = env_flag(
        "VLLM_DISABLE_UVICORN_ACCESS_LOG", True
    )
    enable_request_id_headers: bool = env_flag(
        "VLLM_ENABLE_REQUEST_ID_HEADERS", True
    )
    disable_fastapi_docs: bool = env_flag("VLLM_DISABLE_FASTAPI_DOCS", True)
    trust_remote_code: bool = env_flag("VLLM_TRUST_REMOTE_CODE", False)
    enable_log_requests: bool = env_flag("VLLM_ENABLE_LOG_REQUESTS", False)
    uvicorn_log_level: str = os.getenv("VLLM_UVICORN_LOG_LEVEL", "info")
    root_path: str | None = os.getenv("VLLM_ROOT_PATH")
    allowed_origins: list[str] = None
    allowed_methods: list[str] = None
    allowed_headers: list[str] = None
    ssl_keyfile: str | None = os.getenv("VLLM_SSL_KEYFILE")
    ssl_certfile: str | None = os.getenv("VLLM_SSL_CERTFILE")
    ssl_ca_certs: str | None = os.getenv("VLLM_SSL_CA_CERTS")
    h11_max_header_count: int = int(os.getenv("VLLM_H11_MAX_HEADER_COUNT", "256"))
    extra_args: list[str] = None

    def __post_init__(self) -> None:
        self.api_keys = env_list("VLLM_API_KEYS")
        self.allowed_origins = env_list("VLLM_ALLOWED_ORIGINS") or ["*"]
        self.allowed_methods = env_list("VLLM_ALLOWED_METHODS") or ["*"]
        self.allowed_headers = env_list("VLLM_ALLOWED_HEADERS") or ["*"]
        self.extra_args = shlex.split(os.getenv("VLLM_EXTRA_ARGS", ""))

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
