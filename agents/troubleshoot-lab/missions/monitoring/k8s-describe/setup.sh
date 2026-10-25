#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
t1=$(rand_token)
t2=$(rand_token)
answer_set pod "$t1"
answer_set deploy "$t2"

k -n lab delete pod quiz-describe --ignore-not-found --wait=true >/dev/null
k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: quiz-describe
  namespace: lab
  labels: {lab.quiz: describe}
spec:
  containers:
    - {name: main, image: "busybox:lab-$t1"}
EOF

k -n lab annotate deploy api "lab/quiz=$t2" --overwrite >/dev/null
pull_failed() { k -n lab get events --field-selector involvedObject.name=quiz-describe 2>/dev/null | grep -q Failed; }
wait_until 90 pull_failed
