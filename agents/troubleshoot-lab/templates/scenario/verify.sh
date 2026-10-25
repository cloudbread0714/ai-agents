#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
# 증상이 사라졌으면 0. 특정 수정 방법이 아니라 증상으로 판정하고, 실패 이유를 출력하지 마세요.
need_docker
[[ "$(http_code localhost:8080/healthz)" == 200 ]]
