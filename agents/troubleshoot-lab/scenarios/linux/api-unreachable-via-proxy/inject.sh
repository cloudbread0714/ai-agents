#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
command: ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000"]
YAML
broken() { [[ "$(http_code localhost:8080/api/items)" == 502 ]]; }
wait_until 60 broken
