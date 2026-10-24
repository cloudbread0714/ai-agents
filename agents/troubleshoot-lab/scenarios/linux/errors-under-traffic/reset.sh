#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
"$LAB_ROOT/environment/restore.sh" compose
