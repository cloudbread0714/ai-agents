# Contract: 게시 기록 `data/posted.json` (version 2 확장)

필드 정의와 검증 규칙은 [data-model.md](../data-model.md#dailypost). 이 문서는 파일 예시와 호환 규칙만 다룬다.

## 예시

```json
{
  "version": 2,
  "daily": [
    {
      "date_kst": "2026-10-27",
      "kind": "day",
      "day": 2,
      "main_kind": "scenario",
      "main_id": "site-connection-refused",
      "second_id": null,
      "posted_at": "2026-10-27T02:24:59.706461Z"
    },
    {
      "date_kst": "2026-11-02",
      "kind": "day",
      "day": 3,
      "main_kind": "scenario",
      "main_id": "api-bad-gateway",
      "second_id": null,
      "posted_at": "2026-11-01T23:41:02Z",
      "channel": "C0LABCHANNEL",
      "ts": "1793576462.000100",
      "outcome": "open",
      "resolved_at": null,
      "reminders": ["2026-11-03", "2026-11-04", "2026-11-05"],
      "reposted_at": null
    }
  ],
  "weekly": []
}
```

첫 항목은 기능 도입 전 기록이라 신규 필드가 없고, 끝난 문제로 읽힌다.

## 호환 규칙

- 읽기: 신규 필드가 없으면 `channel/ts/outcome/resolved_at/reposted_at = null`, `reminders = []`.
- 쓰기: 모든 항목을 신규 필드까지 포함해 쓴다(`exclude_none=False`, 기존 저장 방식 그대로).
- 1년 보존 규칙(`RETENTION`)은 그대로다. 단 `outcome=open`인 항목은 기간과 상관없이 지우지 않는다.
- 커밋은 지금처럼 `troubleshoot-lab.yml`의 "Commit posting record" 단계가 `[skip ci]`로 한다.
