#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
t1=$(rand_token)
t2=$(rand_token)
answer_set context kind-troubleshoot-lab
answer_set list "$t1"
answer_set labels "$t2"
k -n lab delete pod -l lab.quiz=get-pods --ignore-not-found --wait=true >/dev/null

k -n lab delete pod quiz-$t1 --ignore-not-found --wait=true >/dev/null
k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: quiz-$t1
  namespace: lab
  labels: {lab.quiz: get-pods, level: "$t2"}
spec:
  containers:
    - {name: main, image: busybox:1.36, command: [sleep, "3600"]}
EOF

k -n lab wait --for=condition=Ready "pod/quiz-$t1" --timeout=120s >/dev/null
