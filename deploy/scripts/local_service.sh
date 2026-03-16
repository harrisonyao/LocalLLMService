#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/src/.env}"
RUNTIME_DIR="${RUNTIME_DIR:-${ROOT_DIR}/.runtime}"
PID_FILE="${PID_FILE:-${RUNTIME_DIR}/local-llm-service.pid}"
LOG_FILE="${LOG_FILE:-${RUNTIME_DIR}/local-llm-service.log}"

if [[ -x "${ROOT_DIR}/venv/bin/python" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/venv/bin/python}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

is_running() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi
}

start_service() {
  mkdir -p "${RUNTIME_DIR}"
  load_env

  if is_running; then
    echo "Service is already running with PID $(cat "${PID_FILE}")."
    echo "Log file: ${LOG_FILE}"
    return 0
  fi

  local check_port="${LLM_PORT:-8000}"
  nohup "${PYTHON_BIN}" "${ROOT_DIR}/src/server_launcher.py" >>"${LOG_FILE}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${PID_FILE}"

  sleep 2
  if kill -0 "${pid}" 2>/dev/null; then
    echo "Service started in background."
    echo "PID: ${pid}"
    echo "Port: ${check_port}"
    echo "Log file: ${LOG_FILE}"
    return 0
  fi

  echo "Service failed to start. Check log: ${LOG_FILE}" >&2
  rm -f "${PID_FILE}"
  return 1
}

stop_service() {
  if ! is_running; then
    rm -f "${PID_FILE}"
    echo "Service is not running."
    return 0
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  kill "${pid}"

  for _ in {1..20}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${PID_FILE}"
      echo "Service stopped."
      return 0
    fi
    sleep 1
  done

  echo "Graceful stop timed out, forcing PID ${pid}."
  kill -9 "${pid}" 2>/dev/null || true
  rm -f "${PID_FILE}"
  echo "Service stopped."
}

status_service() {
  if is_running; then
    echo "Service is running with PID $(cat "${PID_FILE}")."
    echo "Log file: ${LOG_FILE}"
    return 0
  fi

  echo "Service is not running."
  return 1
}

case "${1:-}" in
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    stop_service
    start_service
    ;;
  status)
    status_service
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 1
    ;;
esac
