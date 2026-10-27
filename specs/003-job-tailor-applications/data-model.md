# Data Model: job: 채용 공고별 맞춤 이력서·포트폴리오 준비

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

모든 경로는 `agents/job-apply/` 기준이다. DB는 없고 상태는 파일과 Slack 반응에 있다.

## 1. SourceDocuments (원본 자료)

| 필드 | 설명 |
|------|------|
| `resume_path` | `private/resume.pdf` (읽기 전용) |
| `portfolio_path` | `private/portfolio.pptx` (읽기 전용) |
| `resume_sha256`, `portfolio_sha256` | 처리 시작 시점 해시. 이것이 "원본 버전" 식별자다 |
| `resume_mtime`, `portfolio_mtime` | 사람이 읽기 위한 참고값 |

**규칙**:
- 처리 시작과 끝의 해시가 같아야 한다(FR-007, SC-001). 다르면 그 공고는 `failed`가 되고, "원본이 처리 중에 바뀜"으로 보고한다.
- 새 버전 판단은 따로 하지 않는다. 처리할 때마다 그 시점의 파일을 `base/`로 복사하므로 FR-009가 자연히 지켜진다.

## 2. PostingMessage (공고 메시지, Slack)

| 필드 | 설명 |
|------|------|
| `ts` | Slack 메시지 ts. 채널 안에서 유일한 id |
| `posted_at` | ts를 KST로 바꾼 시각. 정렬 기준(오래된 순) |
| `text` | 메시지 원문 |
| `urls` | 메시지 속 링크 목록(Slack `<url\|label>` 형식 해제). 첫 번째만 처리한다 |
| `state` | `new` / `awaiting_body` / `body_provided` / `done` (아래 상태 기계) |
| `thread_body` | `body_provided`일 때, 봇이 아닌 사용자가 단 스레드 답글을 이어 붙인 텍스트 |
| `is_posting` | 링크가 있거나 본문이 200자 이상이면 공고로 본다. 아니면 목록에서 뺀다 |

**상태 기계** (Slack 반응과 스레드에서 매번 다시 계산하고, 따로 저장하지 않는다):

```text
new ──(가져오기 실패: ❓ + 요청 답글)──▶ awaiting_body
awaiting_body ──(사용자가 스레드에 본문)──▶ body_provided
new / body_provided ──(처리 완료: 답글 + PDF 2개 + ✅)──▶ done
new / body_provided ──(중복이라 건너뜀: 기존 폴더 답글 + ✅)──▶ done
(어느 상태든) ──(사용자가 직접 ✅)──▶ done
```

- `/job-run` 대상은 `new`와 `body_provided`다. `awaiting_body`는 목록에 "본문 대기"로만 나온다(FR-018).
- `[개수]` 제한은 `new`와 `body_provided`를 합쳐 오래된 순으로 적용한다.

## 3. Posting (공고)

수집 단계에서 `.job-state/inbox/<id>.json`에 캐시한다. id는 Slack이면 `ts`, `/tailor`이면 `t-<url_key 해시>`다.

| 필드 | 설명 |
|------|------|
| `id` | 위 규칙 |
| `origin` | `slack` / `direct` |
| `message_ts` | `origin=slack`일 때만 |
| `url` | 원문 링크(없을 수 있음) |
| `url_key` | 중복 판정 키(research R10) |
| `raw_text` | 가져온 본문 또는 사용자가 붙인 본문 |
| `fetch` | `{status: ok \| failed \| skipped, reason?}`. `skipped`는 본문을 직접 받은 경우다 |
| `company`, `role` | 세션이 추출한다. 못 찾으면 사용자에게 받는다 |
| `deadline` | `YYYY-MM-DD` 또는 `null`(상시·미상) |
| `expired` | `deadline < 오늘(KST)` |
| `duplicate_of` | 같은 `url_key`를 가진 `done` 폴더 경로. 없으면 `null` |

## 4. ApplicationFolder (지원 폴더)

`applications/<YYYY-MM-DD>_<회사>_<직무>[_N]/`

```text
meta.json          # 아래 필드
base/
  resume.pdf       # 원본 사본
  resume.txt       # 사본에서 뽑은 텍스트(근거 자료)
  portfolio.pptx   # 원본 사본
  portfolio.json   # 사본 텍스트 구조 덤프(문단 id 포함, contracts/cli.md `dump`)
  render/          # 사본 렌더링(넘침 비교 기준, 미리보기 비교용)
job.md
analysis.md        # frontmatter: fit_score, summary
tailor.json        # 편집 계획(contracts/tailor-plan.schema.json)
resume.md
resume.pdf
portfolio.pptx
portfolio.pdf
preview/slide-NN.png
changes.md         # tailor.json + apply 결과로 생성
```

**meta.json**

| 필드 | 설명 |
|------|------|
| `schema` | `1` |
| `status` | `in_progress` / `done` / `failed` |
| `created_at`, `completed_at` | KST ISO 8601 |
| `posting` | Posting의 `id, origin, message_ts, url, url_key, company, role, deadline` |
| `sources` | SourceDocuments의 해시와 mtime |
| `fit_score` | 0~100 (analysis.md에서 복사) |
| `render` | `{attempts: 0..3, remaining_issues: [RenderIssue]}` |
| `slack` | `{reply_ts?, files_uploaded: bool, reacted: bool}`. 완료 보고를 단계별로 기록해, 다시 실행하면 빠진 단계만 이어서 한다 |
| `error` | `failed`일 때 단계와 요약 |

**상태 기계**:

```text
(init) ─▶ in_progress ─(verify 통과 + 완료 보고)─▶ done
              │                    ▲
              └─(어느 단계든 실패)─▶ failed ─(같은 posting으로 다시 init)─┘ (같은 폴더 재사용)
```

**규칙**:
- `done` 폴더는 CLI가 다시 수정하지 않는다. 같은 공고를 다시 만들 때는 새 폴더를 만든다(FR-016).
- `/tailor`(origin=direct)는 Slack 단계 없이 `verify` 통과로 `done`이 된다.

## 5. FitAnalysis (analysis.md)

frontmatter와 본문 섹션으로 이뤄진다.

```yaml
---
fit_score: 72          # 정수 0~100
summary: "백엔드 경험·Python은 일치, Kubernetes 운영 경험 부족"
---
```

본문 섹션(순서 고정): `## 적합도 근거`, `## 일치하는 점`, `## 부족한 점`, `## 지원 전 보완 제안`

**규칙**:
- `부족한 점`의 요건은 resume.md·portfolio에 나오면 안 된다(FR-012). `verify`가 키워드 단위로 확인한다(아래 7).
- 점수 기준: 필수 요건 충족 비율 70%, 우대 사항 충족 비율 20%, 직무 연차·도메인 일치 10%. 근거 섹션에 계산을 적는다.

## 6. TailorPlan (tailor.json)

전체 스키마는 [contracts/tailor-plan.schema.json](./contracts/tailor-plan.schema.json)에 있다. 요점은 다음과 같다.

- `resume.changes[]`: `{section, before?, after, source, reason}`. resume.md에서 원본과 달라진 부분을 적는다.
- `portfolio.slide_order[]`: base 기준 슬라이드 번호(1부터)의 순열.
- `portfolio.edits[]`: `{slide, shape_id, paragraph, text | runs[] | op: insert_after/delete, source, reason}`
- `source`는 근거 위치다. 예: `resume.txt:L12-14`, `portfolio.json:s3/sh5/p0`. 빈 값은 허용하지 않는다.

## 7. ChangeLog (changes.md, 생성물)

`job apply`가 tailor.json과 적용 결과로 만든다. 세션이 손으로 쓰지 않는다.

1. 사용한 원본: 파일별 해시 앞 12자와 mtime
2. 이력서 변경: 표(섹션 / 전 / 후 / 근거 / 이유)
3. 포트폴리오 슬라이드 순서: base → 결과 대응표
4. 포트폴리오 문구 변경: 표(슬라이드 / 전 / 후 / 근거 / 이유)
5. 렌더링 점검: 시도 횟수, 남은 문제(RenderIssue)
6. 근거 검사 경고(아래 verify 결과)

**근거 검사(`job verify`, 경고 수준)**: 원본 텍스트(`resume.txt` + `portfolio.json`)에 없는데 resume.md나 결과 PPTX에 새로 나온 다음 항목을 찾는다.
- 숫자·퍼센트·연도
- 영문 기술 토큰(대소문자 무시)
- analysis.md `부족한 점`의 키워드

찾은 것은 경고로 보여 준다. 세션은 경고를 고치거나, 근거가 있으면(동의어 등) 이유를 changes.md 경고 섹션에 남긴다.

## 8. RenderIssue

| 필드 | 설명 |
|------|------|
| `slide` | 결과물 기준 슬라이드 번호 |
| `shape_id` | 문제가 생긴 도형 |
| `kind` | `overflow` / `offslide` / `overlap` / `visual`(세션이 이미지로 찾은 문제) |
| `detail` | 넘친 정도(pt) 또는 설명 |

base 렌더링에도 같은 문제(같은 도형·같은 종류)가 있으면 제외한다(research R6).
