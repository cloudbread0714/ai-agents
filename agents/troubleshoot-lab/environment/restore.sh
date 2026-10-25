#!/usr/bin/env bash
# Restore the shared base state (contracts/content.md). Idempotent.
# Usage: restore.sh [all|compose|kind]
#
# A dirty marker ($LAB_STATE/dirty-{compose,kind}) means a scenario or mission may
# have changed live state in ways `apply`/`up` would keep (patched fields,
# disconnected networks), so that side is recreated from scratch.
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"

mode=${1:-all}
mkdir -p "$LAB_STATE"

restore_compose() {
  work_reset
  # Standalone practice containers from missions are all named lab-*.
  local strays
  strays=$(dk ps -aq --filter 'name=^lab-')
  if [[ -n $strays ]]; then
    # shellcheck disable=SC2086
    dk rm -f $strays >/dev/null
  fi
  if [[ -f $LAB_STATE/dirty-compose ]]; then
    # -V: fresh anonymous volumes, so the database is back to its seed data too.
    dc up -d --force-recreate --renew-anon-volumes --remove-orphans --wait
  else
    dc up -d --remove-orphans --wait
    # nginx only reads its config at start; the work copy was just rebuilt.
    dc exec -T nginx nginx -s reload >/dev/null
  fi
  rm -f "$LAB_STATE/dirty-compose"
}

restore_kind() {
  if [[ -f $LAB_STATE/dirty-kind ]]; then
    k delete namespace lab --ignore-not-found --wait=true --timeout=180s
  fi
  k apply -f "$LAB_ROOT/environment/k8s/00-namespace.yaml" >/dev/null
  k -n lab create configmap nginx-conf \
    --from-file=default.conf="$LAB_ROOT/environment/k8s/nginx.conf" \
    --dry-run=client -o yaml |
    k label --local -f - lab.managed=true app=nginx -o yaml |
    k apply -f - >/dev/null
  k -n lab create configmap postgres-init \
    --from-file=init.sql="$LAB_ROOT/environment/postgres/init.sql" \
    --dry-run=client -o yaml |
    k label --local -f - lab.managed=true app=postgres -o yaml |
    k apply -f - >/dev/null
  k apply -f "$LAB_ROOT/environment/k8s/" >/dev/null
  # metrics-server lives in kube-system, outside the namespace reset; apply once.
  if ! k -n kube-system get deploy metrics-server >/dev/null 2>&1; then
    k apply -f "$LAB_ROOT/environment/k8s-addons/metrics-server.yaml" >/dev/null
  fi
  rm -f "$LAB_STATE/dirty-kind"
}

if [[ $mode == all || $mode == compose ]]; then
  restore_compose
fi
if [[ $mode == all || $mode == kind ]]; then
  restore_kind
fi
"$LAB_ROOT/environment/healthcheck.sh" "$mode"
