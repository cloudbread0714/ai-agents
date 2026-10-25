#!/usr/bin/env bash
# Print one hash of the normalized environment state, so sandbox tests can check
# that a reset really returns to the pre-inject state (SC-003).
# Usage: fingerprint.sh [all|compose|kind]
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"

mode=${1:-all}

summary() {
  if [[ $mode == all || $mode == compose ]]; then
    dc config
    dk ps --filter label=com.docker.compose.project=troubleshoot-lab \
      --format '{{.Label "com.docker.compose.service"}} {{.State}} {{.Networks}}' | sort
    (cd "$LAB_WORK" && find . -type f -exec shasum -a 256 {} + | sort)
  fi
  if [[ $mode == all || $mode == kind ]]; then
    k -n lab get deploy,svc,cm -o json | jq -S '
      [.items[]
        | del(.status, .metadata.uid, .metadata.resourceVersion, .metadata.generation,
              .metadata.creationTimestamp, .metadata.managedFields,
              .metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"],
              .metadata.annotations["deployment.kubernetes.io/revision"],
              .spec.clusterIP, .spec.clusterIPs, .spec.template.metadata.annotations)
      ] | sort_by(.kind, .metadata.name)'
  fi
}

summary | shasum -a 256 | cut -d' ' -f1
