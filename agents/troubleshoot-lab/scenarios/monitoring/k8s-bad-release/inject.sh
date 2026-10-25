#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
# A "new release": version 2.0.0 with a wrong DB password, and a readiness probe that only
# checks /version, so Kubernetes happily rolls it out everywhere.
k -n lab patch deploy api --type=strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"api","env":[{"name":"APP_VERSION","value":"2.0.0"},{"name":"DATABASE_URL","value":"postgresql://lab:wrong@postgres:5432/lab"}],"readinessProbe":{"httpGet":{"path":"/version","port":8000}}}]}}}}' >/dev/null
k -n lab rollout status deploy/api --timeout=180s >/dev/null
failing() { [[ "$(http_code localhost:8081/api/items)" != 200 ]]; }
wait_until 60 failing
