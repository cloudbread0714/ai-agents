#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
t1=$(rand_token)
t2=$(rand_token)
answer_set logs "$t1"
answer_set previous "$t2"

k -n lab delete pod quiz-logs --ignore-not-found --wait=true >/dev/null
k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: quiz-logs
  namespace: lab
  labels: {lab.quiz: logs}
spec:
  containers:
    - name: main
      image: busybox:1.36
      command: [sh, -c, "if [ ! -f /data/once ]; then touch /data/once; echo previous run failed: code=$t2; exit 1; fi; echo request_id=$t1 handled; sleep 3600"]
      volumeMounts: [{name: data, mountPath: /data}]
  volumes: [{name: data, emptyDir: {}}]
EOF

restarted() { [ "$(k -n lab get pod quiz-logs -o jsonpath='{.status.containerStatuses[0].restartCount}')" -ge 1 ]; }
wait_until 120 restarted
k -n lab wait --for=condition=Ready pod/quiz-logs --timeout=120s >/dev/null
