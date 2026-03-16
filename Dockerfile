FROM vllm/vllm-openai:v0.17.1

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY server_launcher.py audit_middleware.py unified_client.py README.md ./
COPY deploy ./deploy

EXPOSE 8000

CMD ["python", "server_launcher.py"]
