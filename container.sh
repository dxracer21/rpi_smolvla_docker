#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPOSE_FILE="${SCRIPT_DIR}/compose.yaml"
readonly SERVICE_NAME="smolvla-dev"
readonly CONTAINER_NAME="smolvla-dev"

# Default ROS 2 / Zenoh settings. Values already exported by the user win.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"
export OMY_IP="${OMY_IP:-172.16.101.221}"
export ZENOH_PORT="${ZENOH_PORT:-7447}"
if [[ -z "${ZENOH_CONFIG_OVERRIDE:-}" ]]; then
    export ZENOH_CONFIG_OVERRIDE='mode="client";connect/endpoints=["tcp/'"${OMY_IP}:${ZENOH_PORT}"'"]'
fi

compose() {
    docker compose --file "${COMPOSE_FILE}" --project-directory "${SCRIPT_DIR}" "$@"
}

print_help() {
    cat <<EOF
Usage: $(basename "$0") <command>

Manage the Raspberry Pi ARM64 SmolVLA development container.

Commands:
  start    Create and start the development container
  stop     Stop and remove the development container
  enter    Open an interactive bash shell in the running container
  build    Build the image using the Docker cache
  rebuild  Rebuild without cache and recreate the container
  help     Show this help message

Names:
  service:   ${SERVICE_NAME}
  container: ${CONTAINER_NAME}
  image:     smolvla_rpi:dev

ROS 2 / Zenoh defaults:
  ROS_DOMAIN_ID:         ${ROS_DOMAIN_ID}
  RMW_IMPLEMENTATION:    ${RMW_IMPLEMENTATION}
  ZENOH_CONFIG_OVERRIDE: ${ZENOH_CONFIG_OVERRIDE}
EOF
}

require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "[ERROR] Docker is not installed or is not in PATH." >&2
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "[ERROR] Docker daemon is not running. Start Docker Desktop first." >&2
        exit 1
    fi
}

is_running() {
    [[ -n "$(compose ps --status running --quiet "${SERVICE_NAME}")" ]]
}

build_image() {
    echo "[INFO] Building smolvla_rpi:dev..."
    compose build "${SERVICE_NAME}"
    echo "[INFO] Build complete."
}

start_container() {
    if is_running; then
        echo "[INFO] ${CONTAINER_NAME} is already running."
        return
    fi

    echo "[INFO] Starting ${CONTAINER_NAME}..."
    compose up --detach "${SERVICE_NAME}"
    echo "[INFO] ${CONTAINER_NAME} is running."
}

stop_container() {
    if [[ -z "$(compose ps --all --quiet "${SERVICE_NAME}")" ]]; then
        echo "[INFO] ${CONTAINER_NAME} does not exist."
        return
    fi

    echo "[INFO] Stopping and removing ${CONTAINER_NAME}..."
    compose rm --stop --force "${SERVICE_NAME}"
    echo "[INFO] ${CONTAINER_NAME} removed."
}

enter_container() {
    if ! is_running; then
        echo "[ERROR] ${CONTAINER_NAME} is not running." >&2
        echo "[ERROR] Run '$(basename "$0") start' first." >&2
        exit 1
    fi

    exec docker compose \
        --file "${COMPOSE_FILE}" \
        --project-directory "${SCRIPT_DIR}" \
        exec "${SERVICE_NAME}" bash
}

rebuild_container() {
    echo "[INFO] Rebuilding smolvla_rpi:dev without cache..."
    compose build --no-cache "${SERVICE_NAME}"
    compose up --detach --force-recreate "${SERVICE_NAME}"
    echo "[INFO] Rebuild complete. ${CONTAINER_NAME} is running."
}

main() {
    case "${1:-help}" in
        start)
            require_docker
            start_container
            ;;
        stop)
            require_docker
            stop_container
            ;;
        enter)
            require_docker
            enter_container
            ;;
        build)
            require_docker
            build_image
            ;;
        rebuild)
            require_docker
            rebuild_container
            ;;
        help|-h|--help)
            print_help
            ;;
        *)
            echo "[ERROR] Unknown command: $1" >&2
            print_help >&2
            exit 2
            ;;
    esac
}

main "$@"
