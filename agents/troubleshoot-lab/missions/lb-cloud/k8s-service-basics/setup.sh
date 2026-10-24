#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
t1=$(rand_token)
port=$((3000 + 16#${t1:0:3} % 1000))
answer_set selector "$t1"
answer_set endpoints "$port"
k -n lab delete svc quiz-svc --ignore-not-found >/dev/null

k -n lab delete pod quiz-backend --ignore-not-found --wait=true >/dev/null
k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: quiz-backend
  namespace: lab
  labels: {lab.quiz: service, app: quiz-backend}
spec:
  containers:
    - {name: main, image: busybox:1.36, command: [sleep, "3600"]}
EOF

k apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Service
metadata: {name: quiz-svc, namespace: lab, labels: {lab.quiz: service}}
spec:
  selector: {quiz: "$t1"}
  ports: [{port: 80, targetPort: $port}]
EOF
k -n lab wait --for=condition=Ready pod/quiz-backend --timeout=120s >/dev/null
