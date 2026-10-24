#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
TB_CAPS=NET_ADMIN tb troubleshoot-lab-nginx-1 "iptables -I INPUT -p tcp --dport 80 -j DROP"
hangs() { [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 localhost:8080/healthz || true)" == 000 ]]; }
wait_until 30 hangs
