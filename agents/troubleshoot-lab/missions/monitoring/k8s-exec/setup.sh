#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
t1=$(rand_token)
t2=$(rand_token)
answer_set env "$t1"
answer_set file "$t2"
answer_set dns "$(k -n lab get svc api -o jsonpath='{.spec.clusterIP}')"

k -n lab delete pod quiz-exec --ignore-not-found --wait=true >/dev/null
k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: quiz-exec
  namespace: lab
  labels: {lab.quiz: exec}
spec:
  containers:
    - name: main
      image: busybox:1.36
      command: [sleep, "3600"]
      env: [{name: WORD, value: "$t1"}]
EOF

k -n lab wait --for=condition=Ready pod/quiz-exec --timeout=120s >/dev/null
k -n lab exec quiz-exec -- sh -c "echo $t2 > /tmp/note.txt"
