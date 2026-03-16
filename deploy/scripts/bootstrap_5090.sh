#!/usr/bin/env bash

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/harrisonyao/LocalLLMService.git}"
APP_DIR="${APP_DIR:-/opt/LocalLLMService}"
BRANCH="${BRANCH:-main}"
ENV_TEMPLATE="${ENV_TEMPLATE:-deploy/env.5090.compose.example}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this script as root."
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "Unsupported system: /etc/os-release not found."
  exit 1
fi

. /etc/os-release

if [[ "${ID}" != "ubuntu" ]]; then
  echo "This script currently targets Ubuntu 22.04/24.04."
fi

export DEBIAN_FRONTEND=noninteractive

install_base_packages() {
  apt-get update
  apt-get install -y ca-certificates curl git gnupg lsb-release
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    return
  fi

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | \
    tee /etc/apt/sources.list.d/docker.list >/dev/null

  apt-get update
  apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
}

install_nvidia_container_toolkit() {
  if dpkg -s nvidia-container-toolkit >/dev/null 2>&1; then
    return
  fi

  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null

  apt-get update
  apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
}

sync_repo() {
  if [[ -d "${APP_DIR}/.git" ]]; then
    git -C "${APP_DIR}" fetch origin
    git -C "${APP_DIR}" checkout "${BRANCH}"
    git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
  else
    rm -rf "${APP_DIR}"
    git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
  fi
}

prepare_env() {
  cd "${APP_DIR}"

  if [[ ! -f ".env" ]]; then
    cp "${ENV_TEMPLATE}" .env
    echo "Created ${APP_DIR}/.env from ${ENV_TEMPLATE}"
    echo "Review .env before exposing the service outside your internal network."
  fi
}

start_service() {
  cd "${APP_DIR}"
  docker compose up -d --build
}

print_summary() {
  cat <<EOF

LocalLLMService deployed.

Repository: ${REPO_URL}
Directory:  ${APP_DIR}
Branch:     ${BRANCH}

Useful checks:
  cd ${APP_DIR}
  docker compose ps
  docker logs -f local-llm-service
  curl http://127.0.0.1:8000/health
  nvidia-smi

EOF
}

install_base_packages
install_docker
install_nvidia_container_toolkit
sync_repo
prepare_env
start_service
print_summary
