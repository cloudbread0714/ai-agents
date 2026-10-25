#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
ctx="$LAB_STATE/missions/docker-build/context"
rm -rf "$ctx"
mkdir -p "$ctx"
label=$(rand_token)
answer_set build-label "$label"
cat >"$ctx/Dockerfile" <<EOF
FROM busybox:1.36
LABEL lab.mission="docker-build" lab.build="$label"
RUN od -An -N4 -tx1 /dev/urandom | tr -d ' \\n' > /code
CMD ["sh", "-c", "echo \\"빌드 성공! 확인 코드: lab-\$(cat /code)\\""]
EOF
dk image rm -f lab-hello:practice >/dev/null 2>&1 || true
