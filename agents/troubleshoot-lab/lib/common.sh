# shellcheck shell=bash
# Sourced by every lab script (contracts/content.md). Provides the sandbox guard
# and the only sanctioned ways to reach the environment: k, dc and dk.
#
# Exit codes: 5 = environment not ready (run `make up`), 3 = not the local sandbox.

: "${LAB_ROOT:?LAB_ROOT is not set; run scripts through agents/troubleshoot-lab/bin/lab}"
LAB_STATE="${LAB_STATE:-$LAB_ROOT/.lab-state}"
LAB_WORK="${LAB_WORK:-$LAB_STATE/work}"
LAB_KUBECONFIG="$LAB_ROOT/environment/.kube/config"
LAB_CONTEXT="kind-troubleshoot-lab"
export LAB_STATE LAB_WORK
export KUBECONFIG="$LAB_KUBECONFIG"
export COMPOSE_PROJECT_NAME="troubleshoot-lab"

lab_die() {
  local code=$1
  shift
  echo "lab: $*" >&2
  exit "$code"
}

_LAB_KIND_OK=""
need_kind() {
  [[ -n $_LAB_KIND_OK ]] && return 0
  command -v kubectl >/dev/null || lab_die 5 "kubectl이 없어요. make -C agents/troubleshoot-lab doctor 로 확인하세요"
  [[ -f $LAB_KUBECONFIG ]] || lab_die 5 "kind 클러스터가 준비되지 않았어요. make -C agents/troubleshoot-lab up 을 먼저 실행하세요"
  local ctx server
  ctx=$(command kubectl --kubeconfig "$LAB_KUBECONFIG" config current-context 2>/dev/null) ||
    lab_die 5 "전용 kubeconfig를 읽을 수 없어요. make -C agents/troubleshoot-lab up 을 다시 실행하세요"
  [[ $ctx == "$LAB_CONTEXT" ]] || lab_die 3 "로컬 샌드박스가 아니에요: context가 $LAB_CONTEXT 가 아니라 $ctx 예요"
  server=$(command kubectl --kubeconfig "$LAB_KUBECONFIG" config view --minify \
    -o jsonpath='{.clusters[0].cluster.server}')
  [[ $server =~ ^https://127\.0\.0\.1:[0-9]+$ ]] ||
    lab_die 3 "로컬 샌드박스가 아니에요: API 서버가 127.0.0.1이 아니라 $server 예요"
  command kubectl --kubeconfig "$LAB_KUBECONFIG" --context "$LAB_CONTEXT" get --raw /readyz >/dev/null 2>&1 ||
    lab_die 5 "kind 클러스터가 응답하지 않아요. make -C agents/troubleshoot-lab up 을 실행하세요"
  _LAB_KIND_OK=1
}

_LAB_DOCKER_OK=""
need_docker() {
  [[ -n $_LAB_DOCKER_OK ]] && return 0
  command -v docker >/dev/null || lab_die 5 "docker가 없어요. make -C agents/troubleshoot-lab doctor 로 확인하세요"
  if [[ -n ${DOCKER_HOST:-} && $DOCKER_HOST != unix://* ]]; then
    lab_die 3 "로컬 샌드박스가 아니에요: DOCKER_HOST=$DOCKER_HOST"
  fi
  local endpoint
  endpoint=$(command docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)
  if [[ -n $endpoint && $endpoint != unix://* ]]; then
    lab_die 3 "로컬 샌드박스가 아니에요: docker context 엔드포인트가 $endpoint 예요"
  fi
  command docker info >/dev/null 2>&1 || lab_die 5 "Docker가 실행 중이 아니에요. Docker Desktop을 켠 뒤 make -C agents/troubleshoot-lab up 을 실행하세요"
  _LAB_DOCKER_OK=1
}

# kubectl, pinned to the dedicated kubeconfig and context.
k() {
  need_kind
  command kubectl --kubeconfig "$LAB_KUBECONFIG" --context "$LAB_CONTEXT" "$@"
}

# docker compose, pinned to the lab project and the work-copy override.
dc() {
  need_docker
  command docker compose -p troubleshoot-lab \
    -f "$LAB_ROOT/environment/compose.yaml" -f "$LAB_WORK/compose.override.yaml" "$@"
}

# plain docker (exec, network, inspect) after the same guard.
dk() {
  need_docker
  command docker "$@"
}

# wait_http <url> <expected code> [timeout seconds]
wait_http() {
  local url=$1 want=$2 timeout=${3:-60} code=""
  local deadline=$((SECONDS + timeout))
  while ((SECONDS < deadline)); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" || true)
    [[ $code == "$want" ]] && return 0
    sleep 1
  done
  echo "wait_http: $url returned $code, wanted $want" >&2
  return 1
}

http_code() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$@" || true
}

# http_burst <count> <parallel> <url> [curl args...]: send count requests, at most parallel
# at once; prints one status code per line (000 = no response).
http_burst() {
  local count=$1 parallel=$2 url=$3 i
  shift 3
  local urls=()
  for ((i = 0; i < count; i++)); do urls+=("$url" -o /dev/null); done
  # --parallel-immediate: open all connections at once. Otherwise curl waits for the first
  # response to see whether it can multiplex, and the rest arrive after it (HTTP/1.1).
  curl -s --parallel --parallel-immediate --parallel-max "$parallel" --max-time 5 \
    -w '%{http_code}\n' "$@" "${urls[@]}" || true
}

# http_burst_ok <count> <parallel> <url> [curl args...]: true when every request returned 200.
http_burst_ok() {
  ! http_burst "$@" | grep -qv '^200$'
}

rand_token() {
  od -An -N4 -tx1 /dev/urandom | tr -d ' \n'
}

_answers_file() {
  : "${LAB_ITEM_ID:?LAB_ITEM_ID is not set}"
  echo "$LAB_STATE/missions/$LAB_ITEM_ID/answers.json"
}

# answer_set <step> <value>: remember the value a mission step expects.
answer_set() {
  local file
  file=$(_answers_file)
  mkdir -p "$(dirname "$file")"
  [[ -f $file ]] || echo '{}' >"$file"
  jq --arg k "$1" --arg v "$2" '.[$k] = $v' "$file" >"$file.tmp" && mv "$file.tmp" "$file"
}

answer_get() {
  jq -r --arg k "$1" '.[$k] // empty' "$(_answers_file)" 2>/dev/null
}

_norm() {
  # case, surrounding space, parentheses and _/- differences do not matter: p(95)=p95, close_wait=close-wait
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | tr '_' '-' | tr -d '()' |
    sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# answer_is <step> <given>: case-insensitive exact match after trimming; for expected
# values of 6+ characters, a given text that contains it also passes (pasting the whole
# output line is fine).
answer_is() {
  local want given
  want=$(_norm "$(answer_get "$1")")
  given=$(_norm "${2:-}")
  [[ -n $want ]] || return 1
  [[ $given == "$want" ]] && return 0
  ((${#want} >= 6)) && [[ $given == *"$want"* ]]
}

# wait_until <timeout seconds> <command...>: poll until the command succeeds.
wait_until() {
  local timeout=$1
  shift
  local deadline=$((SECONDS + timeout))
  while ((SECONDS < deadline)); do
    "$@" && return 0
    sleep 1
  done
  return 1
}

# Recreate the work copy from environment/ defaults (research R4).
work_reset() {
  # Empty the work copy but keep $LAB_WORK/nginx itself: nginx bind-mounts it, and on Linux a
  # bind mount follows the directory inode, so a recreated directory would be invisible to it.
  mkdir -p "$LAB_WORK/nginx"
  find "$LAB_WORK" -mindepth 1 -maxdepth 1 ! -name nginx -exec rm -rf {} +
  find "$LAB_WORK/nginx" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  mkdir -p "$LAB_WORK/nginx/locations" "$LAB_WORK/nginx/certs" "$LAB_WORK/override.d"
  cp "$LAB_ROOT/environment/nginx/default.conf" "$LAB_WORK/nginx/default.conf"
  # Practice TLS material generated by `make up` (local only, not a secret).
  if [[ -d $LAB_STATE/certs ]]; then
    cp "$LAB_STATE/certs/"* "$LAB_WORK/nginx/certs/"
  fi
  printf 'services: {}\n' >"$LAB_WORK/compose.override.yaml"
}

# tb <container> <command...>: run the diagnostic toolbox attached to a container's network
# and PID namespaces. Inject/reset only; TB_CAPS=NET_ADMIN adds a capability.
tb() {
  local target=$1
  shift
  dk run --rm --network "container:$target" --pid "container:$target" \
    ${TB_CAPS:+--cap-add "$TB_CAPS"} lab-toolbox:dev sh -c "$*"
}

# compose_override <service>: replace that service's override fragment with stdin
# (YAML indented as the service body), rebuild the override file and restart the service.
compose_override() {
  local service=$1
  {
    echo "  $service:"
    sed 's/^/    /'
  } >"$LAB_WORK/override.d/$service.yaml"
  {
    echo "services:"
    cat "$LAB_WORK"/override.d/*.yaml
  } >"$LAB_WORK/compose.override.yaml"
  dc up -d "$service" >/dev/null 2>&1
}

# sed_inplace <file> <sed expression>: portable across BSD (macOS) and GNU sed.
sed_inplace() {
  sed -e "$2" "$1" >"$1.tmp" && mv "$1.tmp" "$1"
}

# Reload nginx in the compose environment after editing the work copy.
nginx_reload() {
  dc exec -T nginx nginx -s reload >/dev/null
}

# Write an extra nginx location for the compose environment and reload.
nginx_location() {
  local name=$1
  cat >"$LAB_WORK/nginx/locations/$name.conf"
  nginx_reload
}
