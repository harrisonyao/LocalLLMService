FROM vllm/vllm-openai:v0.17.1

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY src ./src
COPY README.md requirements.txt ./
COPY deploy ./deploy

EXPOSE 8000

CMD ["python", "src/server_launcher.py"]
