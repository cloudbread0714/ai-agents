#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  get | stats) answer_is "$step" "$answer" ;;
  ttl) ttl=$(tb troubleshoot-lab-redis-1 "redis-cli TTL lab:mine" | tr -d "[:space:]"); [[ $ttl =~ ^[0-9]+$ ]] && ((ttl > 0)) ;;
  *) exit 1 ;;
esac
