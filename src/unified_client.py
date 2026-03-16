import os
from collections.abc import Iterator

import httpx
from openai import OpenAI


class QwenCoderClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv(
            "OPENAI_BASE_URL", "http://127.0.0.1:8000/v1"
        )
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "sk-local-vllm")
        self.model = model or os.getenv("OPENAI_MODEL", "qwen3-coder")
        timeout = timeout_seconds or float(os.getenv("OPENAI_TIMEOUT_SECONDS", "300"))

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
            http_client=httpx.Client(
                timeout=httpx.Timeout(timeout, connect=5.0, write=30.0),
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                ),
            ),
        )
        self.default_params = {
            "temperature": float(os.getenv("QWEN_TEMPERATURE", "0.2")),
            "top_p": float(os.getenv("QWEN_TOP_P", "0.9")),
            "extra_body": {
                "top_k": int(os.getenv("QWEN_TOP_K", "20")),
                "repetition_penalty": float(
                    os.getenv("QWEN_REPETITION_PENALTY", "1.05")
                ),
            },
        }

    def optimize_code(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是一个精通性能优化的代码专家。"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            **self.default_params,
        )
        return response.choices[0].message.content or ""

    def optimize_code_stream(self, prompt: str) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是一个精通性能优化的代码专家。"},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            **self.default_params,
        )

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content


if __name__ == "__main__":
    coder = QwenCoderClient()
    user_code = "def slow_func(n): return [i * i for i in range(n)]"
    print(coder.optimize_code(f"请优化以下 Python 代码并解释原因：\n{user_code}"))
