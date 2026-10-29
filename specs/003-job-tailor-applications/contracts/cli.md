# Contract: `job` CLI

실행 방법은 `agents/job-apply/bin/job <subcommand>`(= `uv run --package job-apply job ...`)이고, 레포 루트에서 실행한다.
CLI는 결정적인 단계만 맡는다. 판단(추출·분석·작성)은 슬래시 명령을 실행한 세션이 한다([slash-commands.md](./slash-commands.md)).

## 공통 규칙

- 사람이 읽을 출력은 stdout에 쓴다. **마지막 줄**은 항상 `JOB_RESULT <한 줄 JSON>`이다. 세션은 이 줄로 결과를 판단하고, 사용자에게는 보여 주지 않는다.
- 로그(구조화 JSON)는 `.job-state/logs/job.log`와 stderr(WARNING 이상)에 남긴다. 토큰이나 원본 본문은 로그에 남기지 않는다.
- `private/` 아래 파일은 읽기 전용으로만 연다. 모든 서브커맨드는 끝날 때 원본 해시가 시작 때와 같은지 확인한다(다르면 exit 8).

| exit | 의미 |
|------|------|
| 0 | 성공 |
| 1 | 예상하지 못한 오류 |
| 2 | 잘못된 인자 또는 잘못된 `tailor.json`(스키마 위반, `source` 누락 등) |
| 3 | 렌더링 문제가 남아 있음(`apply`) |
| 4 | 디자인 보존 위반(`apply`). 결과 PPTX를 쓰지 않음 |
| 5 | 환경 준비 안 됨(원본 없음, LibreOffice 없음, 토큰 없음, gitignore 미적용) |
| 6 | 이미 처리한 공고(`init`, `--new` 없이) |
| 7 | Slack 오류(재시도 소진) |
| 8 | 명령 실행 중 원본이 바뀜 |
| 9 | 해명되지 않은 근거 검사 경고가 남아 있음(`complete`) |

## `job doctor`

다음을 확인하고 항목별로 ✅/❌를 출력한다.
- 원본 두 파일이 있고 열린다(PDF 텍스트 추출 가능, PPTX 열림).
- `soffice`가 있다.
- PPTX가 쓰는 글꼴이 설치돼 있다(없는 글꼴은 경고만).
- 이력서 글꼴 파일이 있다(없으면 경고만 하고 PyMuPDF 내장 CJK 글꼴을 쓴다).
- `private/`, `applications/`, `.job-state/`가 git에서 무시된다.
- `/job-run`용으로 `SLACK_BOT_TOKEN`과 채널 설정이 있고, `auth.test`와 `conversations.history`(limit=1) 호출이 성공한다.
  실패하면 `slack_ready=false`이고 경고만 한다(`/tailor`는 가능).

`JOB_RESULT {"ok": bool, "slack_ready": bool, "missing": [...], "warnings": [...]}`

## `job inbox [--limit N]`

#job-apply에서 최상위 메시지를 읽어 상태를 계산하고([data-model §2](../data-model.md)), 대상(`new`, `body_provided`)을 오래된 순으로 `N`개까지 수집한다.

- 대상마다 공고 본문을 준비한다.
  - `new`이고 링크가 있으면 가져온다.
  - `body_provided`면 스레드 본문을 쓴다.
  - 링크 없는 긴 메시지는 메시지 본문을 쓴다.
- 가져오기에 실패하면 그 메시지에 ❓ 반응과 본문 요청 답글을 남기고([slack-message.md](./slack-message.md) §2), 결과를 `awaiting_body`로 바꾼다. 같은 실행의 다른 대상은 계속 처리한다.
- 각 대상을 `.job-state/inbox/<id>.json`에 저장하고, `url_key`로 `done` 폴더를 찾아 `duplicate_of`를 채운다.

```json
JOB_RESULT {"items": [{"id": "1729990000.123456", "posted_at": "...", "url": "...", "state": "new",
  "fetch": "ok", "duplicate_of": null, "text_path": ".job-state/inbox/1729990000.123456.txt"}],
  "awaiting_body": [{"id": "...", "url": "..."}], "requested_now": ["..."], "excluded_non_posting": 2}
```

회사·직무·마감일은 CLI가 채우지 않는다. 세션이 `text_path`를 읽어 추출한다.

## `job fetch (<url> | --text-file <path>)`

`/tailor`용이다. id가 `t-<hash>`인 Posting을 만든다. 가져오기에 실패하면 exit 0으로 끝나고 `"fetch": "failed"`를 돌려준다. 그러면 세션이 사용자에게 본문을 요청한다.

`JOB_RESULT {"id": "t-…", "fetch": "ok|failed", "reason": "...", "duplicate_of": null, "text_path": "..."}`

## `job init <id> --company <s> --role <s> [--deadline YYYY-MM-DD] [--new]`

- 중복(`duplicate_of`)이 있는데 `--new`가 없으면 exit 6이다.
- 같은 posting의 `failed`/`in_progress` 폴더가 있으면 그 폴더를 다시 쓴다.
- 폴더를 만들고 다음을 준비한다.
  - `base/`에 원본을 복사한다.
  - `resume.txt`(텍스트 추출)를 만든다. 줄 번호가 근거 위치로 쓰인다.
  - `portfolio.json`(텍스트 구조 덤프)을 만든다.
  - `base/render/`(base 렌더링 PDF와 전체 슬라이드 PNG)를 만든다.
  - `job.md` 머리말(원문 링크, 원문 본문)과 `meta.json`(`in_progress`)을 쓴다.

`JOB_RESULT {"folder": "agents/job-apply/applications/2026-10-27_예시회사_백엔드-개발자", "reused": false}`

**portfolio.json 형식** (세션이 편집 계획을 세울 때 보는 유일한 PPTX 정보):

```json
{"slide_count": 12, "slides": [{"slide": 3, "title": "프로젝트 A",
  "shapes": [{"shape_id": 5, "name": "TextBox 4", "box_pt": [40, 120, 400, 180],
    "paragraphs": [{"paragraph": 0, "text": "…", "runs": ["…", "…"], "level": 0}]}]}]}
```

## `job apply <folder>`

`tailor.json`의 `portfolio` 부분을 base 사본에 적용한다.

1. 스키마와 `source`를 검사한다(실패하면 exit 2).
2. 적용한 뒤 디자인 보존 검사를 한다(research R3). 실패하면 exit 4, 결과물은 쓰지 않는다.
3. `portfolio.pptx`를 쓰고, LibreOffice로 `portfolio.pdf`를 만든다(LibreOffice가 없으면 exit 5).
4. 바뀐 슬라이드(문구 변경이 있는 슬라이드)의 PNG를 `preview/`에 만든다. 이전 미리보기는 지운다.
5. 넘침·겹침을 검출하고 base에 있던 문제는 뺀다(research R6).
6. `meta.render.attempts += 1`. 남은 문제를 기록하고 `changes.md`를 다시 만든다.

이력서 부분은 건드리지 않는다(`resume-pdf` 담당). 다만 `changes.md`의 이력서 표는 tailor.json에서 함께 만든다.

`JOB_RESULT {"attempt": 2, "issues": [{"slide": 4, "shape_id": 7, "kind": "overflow", "detail": "+18pt"}], "previews": ["preview/slide-04.png"]}`

문제가 남아 있으면 exit 3. `attempt`가 3이면 세션은 더 고치지 않고 다음 단계로 간다.

## `job note-issue <folder> --slide N --detail "<text>"`

세션이 미리보기 이미지에서 찾은 문제(`visual`)를 기록한다. `apply`를 다시 실행하면 그 슬라이드의 `visual` 기록은 지워진다(세션이 다시 보고 남은 것만 다시 기록한다).

## `job resume-pdf <folder>`

`resume.md`를 `resume.pdf`로 만든다(research R7). frontmatter는 허용하지 않는다.

## `job verify <folder>`

- 산출물이 모두 있는지 확인한다(FR-010). analysis.md frontmatter의 `fit_score`(0~100 정수)와 `summary`, 정해진 섹션 순서도 확인한다.
- `job.md` 섹션(`## 요약`, `## 자격 요건`, `## 우대 사항`, `## 주요 업무`, `## 기타(근무지·형태·전형)`)이 있는지 확인한다. 완료 보고가 `## 요약`을 쓴다.
- `base/` 사본 해시가 `meta.sources`와 같은지 확인한다.
- 근거 검사 경고를 낸다([data-model §7](../data-model.md)). `tailor.json`의 `acknowledged_warnings`로 해명된 것은 `acknowledged`, 나머지는 `unresolved`로 나눈다.
  `verify` 자체는 exit 0이고, 결과를 `changes.md`에 다시 쓴다.

`JOB_RESULT {"ok": true, "missing": [], "unresolved": [{"file": "resume.md", "token": "Kafka", "kind": "tech"}], "acknowledged": []}`

## `job complete <folder>`

`verify`를 먼저 다시 실행한다. 산출물이 빠졌으면 exit 2, `unresolved` 경고가 남아 있으면 exit 9로 중단한다.
- **origin=slack**: 다음 순서로 보고한다. 각 단계는 `meta.slack`에 기록하고, 다시 실행하면 빠진 단계부터 이어서 한다.
  1. 스레드 답글
  2. PDF 2개 올리기
  3. ✅ 반응
  - 세 단계가 모두 성공해야 `done`이 된다(FR-020).
- **origin=direct**: 바로 `done`이 된다.

`JOB_RESULT {"status": "done", "reply_ts": "...", "fit_score": 72, "remaining_issues": 0}`

## `job skip <id> --reason (duplicate|expired) [--deadline YYYY-MM-DD] [--mark-done]`

`--deadline`은 `expired --mark-done` 답글에 들어갈 마감일이다(세션이 추출한 값, 그때 필수).

- `duplicate`(Slack 공고): 기존 폴더 위치를 스레드에 답글로 남기고 ✅를 단다(FR-016).
- `expired`: 기본은 아무것도 하지 않는다(다음 실행 때 다시 나온다). `--mark-done`이면 "마감이 지나 처리하지 않음" 답글과 ✅를 남긴다.
- origin=direct에서는 Slack 동작 없이 끝난다.

## `job fail <folder> --step <name> --reason "<text>"`

세션 쪽 단계(분석·작성)에서 실패했을 때 `meta.status = failed`로 기록한다. Slack에는 아무것도 남기지 않는다(FR-019).

## `job status [--all]`

`applications/` 폴더 목록을 날짜·회사·직무·상태·적합도와 함께 보여 준다. 기본은 최근 20개다.
