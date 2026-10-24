#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
# 장애 주입. environment/ 의 기본 파일은 건드리지 말고 작업 사본($LAB_WORK)과 실행 중인 리소스만 바꾸세요.
# 증상이 실제로 재현된 뒤에 0으로 끝나야 해요.
need_docker
broken() { [[ "$(http_code localhost:8080/healthz)" != 200 ]]; }
wait_until 30 broken
