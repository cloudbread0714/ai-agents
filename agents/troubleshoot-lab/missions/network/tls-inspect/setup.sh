#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set issuer "troubleshoot-lab CA"
answer_set san nginx
answer_set trust 60
