# Practice environment: docker compose + kind cluster "troubleshoot-lab".
# Run from the repo root as `make -C agents/troubleshoot-lab <target>`.

LAB_ROOT := $(abspath .)
LAB_STATE := $(LAB_ROOT)/.lab-state
LAB_WORK := $(LAB_STATE)/work
LAB_KUBECONFIG := $(LAB_ROOT)/environment/.kube/config
export LAB_ROOT LAB_STATE LAB_WORK

.PHONY: doctor up down status env test-sandbox

doctor:
	@missing=0; \
	for t in docker kind kubectl jq curl uv; do \
	  command -v $$t >/dev/null || { echo "없음: $$t"; missing=1; }; \
	done; \
	if command -v docker >/dev/null && ! docker info >/dev/null 2>&1; then \
	  echo "Docker가 실행 중이 아니에요 (Docker Desktop을 켜 주세요)"; missing=1; \
	fi; \
	if [ $$missing = 0 ]; then echo "준비 완료"; fi; \
	exit $$missing

up: doctor
	docker build -q -t lab-api:dev environment/api
	docker build -q -t lab-toolbox:dev environment/toolbox
	docker pull -q grafana/k6:1.0.0
	@mkdir -p $(LAB_STATE)/certs
	docker run --rm -v $(LAB_STATE)/certs:/certs -v $(LAB_ROOT)/environment/certs:/scripts:ro \
	  lab-toolbox:dev sh /scripts/generate.sh
	@mkdir -p $(dir $(LAB_KUBECONFIG))
	@kind get clusters 2>/dev/null | grep -qx troubleshoot-lab || \
	  kind create cluster --config environment/kind/cluster.yaml --kubeconfig $(LAB_KUBECONFIG)
	@kind export kubeconfig --name troubleshoot-lab --kubeconfig $(LAB_KUBECONFIG) >/dev/null
	kind load docker-image lab-api:dev lab-toolbox:dev --name troubleshoot-lab
	environment/restore.sh all
	@echo "실습 환경 준비 완료: compose http://localhost:8080 · kind http://localhost:8081"

down:
	-@bash -c 'source lib/common.sh && mkdir -p "$$LAB_WORK" && touch "$$LAB_WORK/compose.override.yaml" && dc down -v --remove-orphans'
	-kind delete cluster --name troubleshoot-lab --kubeconfig $(LAB_KUBECONFIG)
	rm -rf $(LAB_WORK) $(LAB_STATE)/dirty-* environment/.kube

status:
	-@bash -c 'source lib/common.sh && dc ps'
	-@bash -c 'source lib/common.sh && k -n lab get pods'

env:
	@echo 'export KUBECONFIG=$(LAB_KUBECONFIG)'

test-sandbox:
	cd ../.. && LAB_SANDBOX=1 uv run pytest -m sandbox agents/troubleshoot-lab/tests/sandbox
