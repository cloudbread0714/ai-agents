# Contract: 측정 (`lab measure`)

FR-016~FR-019와 research R20을 구현하는 계약이다.

## 입력

- 진행 중 시나리오의 `measure` 정의(data-model.md MeasureSpec)와 `env`
- 단계(phase)는 상태로 정한다.
  - `fault_injected` 이전: `baseline`
  - 이후: `fault`
  - `scenario_solved` 이후: `after`

## 실행

| 항목 | compose | kind |
|------|---------|------|
| k6 실행 | `dk run --rm --network troubleshoot-lab_lab -v <out>:/out grafana/k6:1.0.0 run /scripts/measure.js` | `dk run --rm --network kind ...` |
| 대상 URL | `http://nginx<path>`, https면 `https://nginx:443<path>` (실습 CA 마운트) | `http://troubleshoot-lab-control-plane:30080<path>` |
| 자원 샘플 | 1초마다 `dk stats --no-stream <service 컨테이너>` | 5초마다 `k -n lab top pod -l app=<service>` (metrics-server) |

- k6에는 환경변수 `TARGET_URL`, `METHOD`, `BODY`, `VUS`, `DURATION`을 넘긴다.
- 스크립트는 `environment/k6/measure.js` 하나다.
  - 응답 시간 통계는 `expected_response:true` 하위 지표를 쓴다.
  - 결과는 `handleSummary`로 `/out/summary.json`에 쓴다.
- 전체 제한 시간은 `duration_s + 20`초이고, 넘으면 측정 실패(outcome `failed`)다. 실패한 측정은 기록하지 않는다.
- 측정 전에 가드를 실행한다(FR-024).
- 대상 호스트는 위 표의 내부 주소로 고정한다(FR-027).

## 기록

```json
{"type": "measured", "attempt": 1, "phase": "baseline",
 "metrics": {"avg_ms": {"value": 12.4}, "p95_ms": {"value": 30.1}, "rps": {"value": 210.5},
             "error_rate": {"value": 0.0}, "requests": {"value": 4210},
             "cpu_avg_pct": {"value": 18.2}, "cpu_max_pct": {"value": 35.0}, "mem_max_mib": {"value": 61.3}}}
```

| 상황 | 기록 |
|------|------|
| 성공 요청 0건 | `avg_ms`, `p95_ms` = `{"status": "not_applicable"}`, `error_rate` = 1.0 |
| 자원 샘플 0개 | `cpu_*`, `mem_max_mib` = `{"status": "unavailable"}` |
| `--skip "사유"` | 모든 지표 `{"status": "skipped"}`, `skip_reason` 기록 |

## 출력 (stdout)

```
📏 측정 완료 (정상 상태, 20초, 5 VU, GET /api/items)
| 지표 | 값 |
| 평균 응답 시간 | 12.4 ms |
| p95 응답 시간 | 30.1 ms |
| 처리량 | 210.5 req/s |
| 오류율 | 0.0 % |
| CPU 평균/최대 | 18.2 % / 35.0 % |
| 메모리 최대 | 61.3 MiB |
```

같은 시도의 baseline이 있으면 fault·after 측정 출력에 "정상 대비" 열을 붙인다. 이 열은 두 값이 모두 실측값일 때만 계산하고, 하나라도 상태값이면 "—"로 둔다.
