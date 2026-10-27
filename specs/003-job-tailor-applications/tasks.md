---

description: "Task list for job: 채용 공고별 맞춤 이력서·포트폴리오 준비"
---

# Tasks: job: 채용 공고별 맞춤 이력서·포트폴리오 준비

**Input**: Design documents from `/specs/003-job-tailor-applications/`

**Prerequisites**: plan.md, spec.md, research.md(R1–R13), data-model.md, contracts/(cli, slash-commands, slack-message, tailor-plan.schema.json), quickstart.md

**Starting point**: `agents/job-apply/`는 비어 있다(`.env`만 있음, gitignore됨). `shared`의 retry·logging·config·files는 `main`에 있다.

**Tests**:
- 헌법 III에 따라 테스트 작업을 포함한다. 각 스토리에서 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.
- Slack과 웹은 `pytest-httpx`로 모킹한다. LibreOffice가 필요한 검증은 `-m render`(`JOB_RENDER=1`)로만 실행한다.
- 테스트 데이터는 모두 가상 인물이다. 실제 이력서·포트폴리오를 테스트에 쓰지 않는다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1(/tailor 맞춤 자료), US2(디자인 보존·렌더링 점검), US3(/job-run Slack 일괄 처리), US4(❓ 본문 요청), US5(원본 교체)

## Path Conventions

- 에이전트: `agents/job-apply/` (항상 전체 경로로 쓴다)
- Python: `agents/job-apply/src/job_apply/`, 테스트: `agents/job-apply/tests/`
- CLI 계약: [contracts/cli.md](./contracts/cli.md). 모든 서브커맨드는 마지막 줄에 `JOB_RESULT <json>`을 출력하고, 표의 종료 코드를 따른다.

---

## Phase 1: Setup

- [ ] T001 Create `agents/job-apply/pyproject.toml`, following `agents/troubleshoot-lab/pyproject.toml`
  - name `job-apply`; script `job = "job_apply.cli:main"`; hatchling; `packages = ["src/job_apply"]`
  - dependencies: `shared`, `httpx`, `python-pptx>=1.0,<2`, `pymupdf>=1.24`, `trafilatura>=2.0`, `markdown>=3.7`, `jsonschema>=4.23`, `pydantic>=2.7`, `pyyaml>=6.0`
  - `[tool.pytest.ini_options]`: `pythonpath = ["src", "../../shared/src", "tests"]`, marker `render: needs LibreOffice (JOB_RENDER=1)`
  - create empty `agents/job-apply/src/job_apply/__init__.py` and `agents/job-apply/src/job_apply/__main__.py` (calls `cli.main`)
- [ ] T002 Update root `pyproject.toml`
  - add `agents/job-apply/tests` to `testpaths`; add `agents/job-apply/src` and `agents/job-apply/tests` to `pythonpath`
  - add `job_apply` and `ja_support` to isort `known-first-party`
  - add marker `render: needs LibreOffice (JOB_RENDER=1)`
  - run `uv lock` and `uv sync --all-packages` and commit `uv.lock`
- [ ] T003 [P] Update `.gitignore` (research R11)
  - replace `agents/job-apply/data/private/` with `agents/job-apply/private/`, `agents/job-apply/applications/`, `agents/job-apply/.job-state/`
  - keep `*.resume.*`
- [ ] T004 [P] Create `agents/job-apply/bin/job`, mirroring `agents/troubleshoot-lab/bin/lab` (PYTHONPATH with `shared/src` and `agents/job-apply/src`, `uv run --quiet --project "$ROOT" --package job-apply python -m job_apply "$@"`); make it executable
- [ ] T005 [P] Create `agents/job-apply/.env.example` with only `SLACK_BOT_TOKEN=`; remove `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL_MAIN` and `SLACK_WEBHOOK_URL_TEST` from the local `agents/job-apply/.env` only if they are still empty (research R1)
- [ ] T006 [P] Create `agents/job-apply/config/job.yaml`
  - `slack.channel_id: ""` (filled by the user; not a secret)
  - `resume.font_files`: candidate paths in order Pretendard → Noto Sans KR → AppleSDGothicNeo
  - `fetch`: `timeout_s: 15`, `min_chars: 400`, `user_agent`
  - `render`: `timeout_s: 120`, `max_attempts: 3`, `overflow_tolerance_pt: 4`, `preview_dpi: 150`
- [ ] T007 [P] Create `agents/job-apply/templates/resume.css` (A4, 18mm margins, one Korean font family, h1/h2/ul styles, no colors beyond one accent)
- [ ] T008 [P] Create the test helper package `agents/job-apply/tests/ja_support/__init__.py` (like `tl_support`; no `tests/__init__.py`, imports via `--import-mode=importlib`) and `agents/job-apply/tests/fixtures/.gitkeep`

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T009 [P] Add Slack bot/user token masking to `shared/src/shared/logging.py` (`xox[abpr]-[A-Za-z0-9-]+` → `xox?-***`) and a test in `shared/tests/test_logging.py` (create if missing). Constitution IV/V
- [ ] T010 [P] Write sample-data builders in `agents/job-apply/tests/ja_support/samples.py`
  - `make_resume_pdf(path, lines)`: PyMuPDF PDF with Korean text (fictional person "홍길동", fictional companies)
  - `make_portfolio_pptx(path)`: python-pptx deck of 5 slides with a title slide, a 2-run paragraph (bold + normal), a bullet list, an image shape, a small text box (for overflow tests), and one slide whose text box already overlaps a decoration in the original (for "base issue excluded" tests)
  - `make_posting_html(kind)`: `jsonld`, `next_data`, `plain`, `login_wall`, `too_short`
- [ ] T011 [P] Write `agents/job-apply/tests/ja_support/fake_render.py`: a renderer that turns a PPTX into a PDF without LibreOffice (one page per slide, each text frame drawn at its box with PyMuPDF `insert_textbox`, text that does not fit drawn past the box bottom), so overflow detection can be tested deterministically
- [ ] T012 Create `agents/job-apply/tests/conftest.py`: `job_root` fixture (tmp copy of `agents/job-apply/` layout with `private/`, `applications/`, `.job-state/`, `config/job.yaml`), sample originals from T010, `fake_renderer` from T011, fixed KST clock `2026-10-27T10:00+09:00`, `httpx_mock` re-export
- [ ] T013 Write tests in `agents/job-apply/tests/test_config.py`: load `config/job.yaml` via `shared.config.load_yaml`; reject secret-looking keys; `SLACK_BOT_TOKEN` via `require_env` only when Slack is needed
- [ ] T014 Implement `agents/job-apply/src/job_apply/config.py`: pydantic `JobConfig` for T006 fields and a `Paths` object (root, private, applications, state, templates) resolved from the agent directory; `slack_token()` uses `shared.config.require_env("SLACK_BOT_TOKEN")`
- [ ] T015 Write tests in `agents/job-apply/tests/test_models.py` for data-model rules
  - `Posting.deadline` is `YYYY-MM-DD` or `null`; `expired` is `deadline < today(KST)`
  - `Meta.status` is one of `in_progress` / `done` / `failed`; `fit_score` is an integer 0–100
  - `RenderIssue.kind` is one of `overflow` / `offslide` / `overlap` / `visual`
  - `TailorPlan` validates against `specs/003-job-tailor-applications/contracts/tailor-plan.schema.json`; in addition the CLI checks: `slide_order` is a permutation of `1..slide_count`; each edit has exactly one of `text` / `runs` / `op`; `source` may not be empty
- [ ] T016 Implement `agents/job-apply/src/job_apply/models.py` (Posting, Meta, Sources, SlackProgress, RenderIssue, TailorPlan) and copy the JSON schema to `agents/job-apply/src/job_apply/schema/tailor-plan.schema.json` (package data; a test asserts it equals the contract file)
- [ ] T017 Write tests in `agents/job-apply/tests/test_sources.py`
  - missing or unreadable original → `SourceError` naming the file (exit 5)
  - SHA-256 of both originals; `guard()` context manager raises `SourceChangedError` (exit 8) if a hash differs at exit
  - originals are opened read-only: after any call, bytes and mtime are unchanged
  - `extract_resume_text()` writes numbered-line text usable as `resume.txt:L<n>`
- [ ] T018 Implement `agents/job-apply/src/job_apply/sources.py` (hashing, guard, copy to `base/`, resume text extraction with PyMuPDF)
- [ ] T019 Write tests in `agents/job-apply/tests/test_folders.py` (research R12)
  - name `YYYY-MM-DD_<회사>_<직무>`: NFC, strip `/\:*?"<>|` and control chars, spaces → `-`, 40 chars per part
  - collision → `_2`, `_3`; an existing `done` folder is never reused
  - same posting with `failed` / `in_progress` folder → reused
  - meta transitions: `in_progress → done`, `in_progress → failed`, `failed → in_progress`; `done` is terminal
  - meta writes are atomic (`shared.files.write_text_atomic`)
- [ ] T020 Implement `agents/job-apply/src/job_apply/folders.py`
- [ ] T021 Write tests in `agents/job-apply/tests/test_render.py`
  - `Renderer` protocol: `to_pdf(pptx, out_dir) -> Path`
  - `SofficeRenderer` builds `soffice --headless -env:UserInstallation=file://<.job-state/lo-profile> --convert-to pdf --outdir …`, enforces `render.timeout_s`, logs failures; missing `soffice` → `EnvNotReady` (exit 5). Use a fake runner, no real LibreOffice
  - `render_previews(pdf, pages, out_dir, dpi)` writes `slide-NN.png` (NN = result order, zero-padded) and deletes previous previews
  - `@pytest.mark.render` test (skipped unless `JOB_RENDER=1`) converts the sample deck with real LibreOffice
- [ ] T022 Implement `agents/job-apply/src/job_apply/render.py`
- [ ] T023 Write tests in `agents/job-apply/tests/test_cli.py` for the CLI frame: argparse subcommands from contracts/cli.md; last stdout line is `JOB_RESULT <one-line JSON>`; exception → exit code mapping (2, 4, 5, 6, 7, 8, else 1); logs go to `.job-state/logs/job.log` with `shared.logging`
- [ ] T024 Implement `agents/job-apply/src/job_apply/cli.py` frame (subcommand registry, `emit_result()`, error → exit code mapping, every subcommand runs inside `sources.guard()`)

**Checkpoint**: 기본 틀 완료 — `uv run pytest agents/job-apply`가 통과하고, `agents/job-apply/bin/job --help`가 동작한다.

---

## Phase 3: User Story 1 - 공고 하나로 맞춤 지원 자료 만들기 (Priority: P1) 🎯 MVP

**Goal**: `/tailor <링크|본문>`으로 FR-010 산출물이 모두 든 지원 폴더가 만들어지고, 원본은 그대로다.

**Independent Test**: 샘플 원본과 샘플 공고로 `fetch → init → (세션 산출물 대신 픽스처 job.md·analysis.md·resume.md·tailor.json) → resume-pdf → apply → verify → complete`를 실행하면, 폴더 산출물이 모두 있고 `meta.status=done`이며, 원본 해시가 같다.

### Tests for User Story 1

- [ ] T025 [P] [US1] Write tests in `agents/job-apply/tests/test_fetch.py` (research R8): JSON-LD `JobPosting` and `__NEXT_DATA__` preferred over trafilatura; `plain` extracted; `too_short` (< `fetch.min_chars`) and `login_wall` → `failed` with reason; HTTP 403 → `failed` without retry; 5xx/timeout retried 3 times via `shared.retry` then `failed`; `--text-file` → `fetch: skipped`
- [ ] T026 [P] [US1] Write tests in `agents/job-apply/tests/test_dedup.py` (research R10): `url_key` lowercases scheme/host, drops `utm_*`, `ref`, `fbclid`, `gclid`, fragment and trailing `/`, keeps other query params sorted; text-only key is `text:<sha256[:16]>`; only `done` folders count as duplicates
- [ ] T027 [P] [US1] Write tests in `agents/job-apply/tests/test_pptx_dump.py`: `portfolio.json` has `slide_count`, per slide `slide`, `title`, `shapes[].shape_id/name/box_pt/paragraphs[].paragraph/text/runs/level`; text frames inside groups are listed with their own `shape_id`; tables are listed with `"table": true` and no paragraphs (not editable in this version)
- [ ] T028 [P] [US1] Write tests in `agents/job-apply/tests/test_pptx_apply.py` (research R3)
  - `text` replaces the paragraph: first run keeps its `a:rPr`, other runs removed
  - `runs` requires the same run count as the original
  - `op.insert_after` clones the paragraph's `a:pPr`/first `a:rPr`; `op.delete` removes it; both only inside the same shape
  - `slide_order` reorders `p:sldIdLst` only
  - unknown slide / shape / paragraph → `PlanError` (exit 2)
- [ ] T029 [P] [US1] Write tests in `agents/job-apply/tests/test_resume_pdf.py`: `resume.md` → A4 PDF via PyMuPDF `Story` with `templates/resume.css` and the first existing font in `resume.font_files`; when none exists, falls back to the PyMuPDF built-in CJK font (`fitz.Font("cjk")`) so the test passes on Ubuntu CI without system fonts (research R7); Korean text is extractable from the result; frontmatter in resume.md → exit 2
- [ ] T030 [P] [US1] Write tests in `agents/job-apply/tests/test_changes.py`: `changes.md` sections in the data-model §7 order (사용한 원본 해시 앞 12자 + mtime, 이력서 변경 표, 슬라이드 순서 대응표, 포트폴리오 문구 표, 렌더링 점검, 근거 검사 경고); `|` and newlines in cells escaped
- [ ] T031 [P] [US1] Write tests in `agents/job-apply/tests/test_verify.py`
  - missing artifact from FR-010 → `ok: false` with `missing`
  - analysis.md: frontmatter `fit_score` (integer 0–100) and `summary` required; sections exactly `## 적합도 근거`, `## 일치하는 점`, `## 부족한 점`, `## 지원 전 보완 제안` in this order
  - `base/` hashes must equal `meta.sources`
  - job.md sections `## 요약`, `## 자격 요건`, `## 우대 사항`, `## 주요 업무`, `## 기타(근무지·형태·전형)` required (the completion reply reads `## 요약`)
  - provenance warnings (verify itself exits 0): numbers/percent/years and Latin tech tokens in resume.md or result PPTX text that are absent from `base/resume.txt` + `base/portfolio.json`, and `부족한 점` keywords appearing in resume.md/PPTX
  - warnings matched by `tailor.json` `acknowledged_warnings` (`file` + `token`) are reported as `acknowledged`, the rest as `unresolved`; both listed in `changes.md`
- [ ] T032 [US1] Write the US1 flow test in `agents/job-apply/tests/test_flow_tailor.py`: run `fetch` (mocked URL), `init`, write fixture session outputs, `resume-pdf`, `apply` (fake renderer), `verify`, `complete` through `cli.main`; assert FR-010 artifacts, `meta.status=done`, origin `direct` makes no HTTP call to Slack, original hashes unchanged (SC-001); a resume.md with an unsupported "Kafka" → `complete` exit 9 and status stays `in_progress`, then acknowledging it in `tailor.json` (or removing it) lets `complete` succeed; `fetch` + `init` again with the same URL (plus `?utm_source=x`) → exit 6; with `--new` → a new folder `<same name>_2`, the first folder unchanged

### Implementation for User Story 1

- [ ] T033 [P] [US1] Implement `agents/job-apply/src/job_apply/fetch.py` (httpx + `shared.retry`, JSON-LD/NEXT_DATA, trafilatura, failure rules, `.job-state/inbox/<id>.json` + `<id>.txt`)
- [ ] T034 [P] [US1] Implement `agents/job-apply/src/job_apply/dedup.py`
- [ ] T035 [P] [US1] Implement `agents/job-apply/src/job_apply/pptx_dump.py`
- [ ] T036 [US1] Implement `agents/job-apply/src/job_apply/pptx_apply.py` (depends on T035 for ids)
- [ ] T037 [P] [US1] Implement `agents/job-apply/src/job_apply/resume_pdf.py`
- [ ] T038 [P] [US1] Implement `agents/job-apply/src/job_apply/changes.py`
- [ ] T039 [P] [US1] Implement `agents/job-apply/src/job_apply/verify.py`
- [ ] T040 [US1] Wire subcommands in `agents/job-apply/src/job_apply/cli.py`: `fetch`, `init` (base copy, `resume.txt`, `portfolio.json`, `base/render/` via renderer, `job.md` header with link and raw text, meta `in_progress`; duplicate → exit 6 unless `--new`), `resume-pdf`, `apply` (apply → write `portfolio.pptx` → PDF → previews of changed slides → `changes.md`; `meta.render.attempts += 1`), `verify`, `complete` (re-runs verify; missing artifacts → exit 2, `unresolved` warnings → exit 9; origin `direct` → `done`; terminal summary adds "⚠️ 낮은 적합도" when `fit_score < 40`), `fail`, `status`
- [ ] T041 [US1] Write tests in `agents/job-apply/tests/test_doctor.py` and implement `agents/job-apply/src/job_apply/doctor.py` + `doctor` subcommand: originals open, `soffice` present, PPTX fonts vs `fc-list` (warning; skipped if `fc-list` missing), resume font present (warning; built-in CJK fallback), `git check-ignore` for `private/`, `applications/`, `.job-state/` (fail if not ignored), `slack_ready` = token + `slack.channel_id` + successful `auth.test` and `conversations.history(limit=1)` (warning only; research R9). Tests fake the git and process runner (the `job_root` fixture is not a git repo) and mock Slack with `httpx_mock`
- [ ] T042 [US1] Create `.claude/commands/tailor.md` per contracts/slash-commands.md (`disable-model-invocation: true`, `argument-hint: <공고 링크 또는 본문>`; steps 1–5, 공고별 처리 1–10, 규칙 1–7)
- [ ] T043 [US1] Update `.claude/settings.json`: allow `Bash(agents/job-apply/bin/job doctor:*)`, `fetch`, `init`, `resume-pdf`, `apply`, `note-issue`, `verify`, `complete`, `status`, `fail`; deny `Edit(agents/job-apply/private/**)` and `Write(agents/job-apply/private/**)` (research R11)

**Checkpoint**: US1 완료 — `/tailor`로 지원 폴더 하나가 끝까지 만들어진다(MVP). 단, 디자인 보존 검사와 넘침 검출은 US2에서 붙으므로, 실제 포트폴리오에 쓰기 전에 US2까지 마친다.

---

## Phase 4: User Story 2 - 포트폴리오 디자인을 지키며 공고에 맞추기 (Priority: P1)

**Goal**: 텍스트와 순서 외 변경은 막히고, 넘침·겹침은 자동 검출되며, 세션의 이미지 확인과 최대 3회 재시도 결과가 기록된다.

**Independent Test**: 샘플 덱에 긴 문구 편집을 적용하면 `overflow`가 보고된다(exit 3). 원본에 이미 있던 겹침은 보고되지 않는다. 문구를 줄여 다시 적용하면 exit 0이다. 디자인 속성을 바꾸려 하면 exit 4가 나고 출력 파일이 생기지 않는다.

### Tests for User Story 2

- [ ] T044 [P] [US2] Write tests in `agents/job-apply/tests/test_design_guard.py` (research R3 checks 1–4): pass for text-only + reorder; fail when a shape's position/size, fill, picture, layout reference, theme/master/media part, or an `a:rPr` not present in that shape's original changes (inject each mutation directly into the output XML); on failure no `portfolio.pptx` is written
- [ ] T045 [P] [US2] Write tests in `agents/job-apply/tests/test_layout_check.py` (research R6) with `fake_render`: text past its box by > `overflow_tolerance_pt` → `overflow` with `+Npt`; past slide bounds → `offslide`; two text shapes intersecting → `overlap`; issues also present in `base/render/` (same shape, same kind) are excluded
- [ ] T046 [US2] Extend `agents/job-apply/tests/test_flow_tailor.py`: attempt 1 with a long edit → exit 3 and issue listed; `note-issue --slide 2 --detail …` recorded as `visual`; attempt 2 with a shorter edit → exit 0, `visual` issues on re-applied slides cleared; after attempt 3 (3 applies in total, counting the first; FR-014) with issues left, `changes.md` "렌더링 점검" and `complete` result list them (`remaining_issues`)

### Implementation for User Story 2

- [ ] T047 [P] [US2] Implement `agents/job-apply/src/job_apply/design_guard.py`
- [ ] T048 [P] [US2] Implement `agents/job-apply/src/job_apply/layout_check.py` (PyMuPDF line bboxes vs PPTX text frame boxes in pt; map PDF page ↔ result slide order)
- [ ] T049 [US2] Integrate into `apply` in `agents/job-apply/src/job_apply/cli.py`: run `design_guard` before writing (exit 4), then `layout_check` against base issues, store `meta.render.remaining_issues`, exit 3 when issues remain; add `note-issue` subcommand
- [ ] T050 [US2] Add the rendering-check loop wording to `.claude/commands/tailor.md` (공고별 처리 7: open every `preview/` PNG with Read, shorten text only, max 3 attempts, `note-issue` for visual problems left after attempt 3)
- [ ] T051 [US2] Add a `@pytest.mark.render` test in `agents/job-apply/tests/test_render.py` that applies a long edit to the sample deck with real LibreOffice and asserts `overflow` is detected and the pre-existing overlap is not

**Checkpoint**: US1 + US2 — `/tailor` 결과 포트폴리오의 디자인이 보존되고 렌더링 점검이 돈다.

---

## Phase 5: User Story 3 - Slack에 모아 둔 공고를 한 번에 처리하기 (Priority: P2)

**Goal**: `/job-run [개수]`가 ✅ 없는 공고를 오래된 순으로 처리한다. 처리 전 목록과 확인을 거치고, 완료하면 답글·PDF 2개·✅를 남긴다.

**Independent Test**: 가짜 Slack에 ✅ 메시지 1개, 공고 메시지 3개, 잡담 1개를 두고 `inbox --limit 2` → 처리 → `complete`를 실행한다. 가장 오래된 2개만 대상이 되고, 각각 답글·파일·✅가 순서대로 호출된다. 다시 `inbox`를 실행하면 대상이 0건이다.

### Tests for User Story 3

- [ ] T052 [P] [US3] Write tests in `agents/job-apply/tests/test_slack_api.py` (research R9) with `httpx_mock`: `conversations.history` pagination (`response_metadata.next_cursor`), `conversations.replies`, `reactions.add` (`already_reacted` treated as success), `chat.postMessage` with `thread_ts`, upload flow `files.getUploadURLExternal` ×2 → upload POSTs → one `files.completeUploadExternal` with `channel_id` + `thread_ts`; 429 honors `Retry-After`; `ok:false` `ratelimited`/`internal_error` retried, other errors raise `SlackError` (exit 7); token never appears in logs or exception text
- [ ] T053 [P] [US3] Write tests in `agents/job-apply/tests/test_inbox.py` (data-model §2): only top-level messages; `is_posting` = has link or text ≥ 200 chars, others counted in `excluded_non_posting`; Slack `<url|label>` unwrapped, first URL used, extra URLs kept for the reply; state from reactions (`white_check_mark` → done regardless of who reacted); oldest first; `--limit N` applied to `new` + `body_provided` together; `duplicate_of` filled from `done` folders
- [ ] T054 [P] [US3] Write tests in `agents/job-apply/tests/test_report.py` (contracts/slack-message.md §1, §3, §4): completion text (마감 D-n, 적합도 with "⚠️ 낮은 적합도" prefix when `fit_score < 40`, summary, 요약 3줄 from `job.md ## 요약`, folder path, 렌더링 상태, 처리하지 않은 링크, "제출은 직접 해 주세요."), mrkdwn escaping of company/role; file names `<회사>_<직무>_resume.pdf` / `_portfolio.pdf`; duplicate and expired texts
- [ ] T055 [US3] Write the US3 flow test in `agents/job-apply/tests/test_flow_job_run.py`: fake channel as above; `inbox --limit 2`; process both with fixture session outputs; `complete` calls reply → upload → ✅ in order and records `meta.slack`; failing upload (5xx exhausted) → exit 7, no ✅, `meta.status` stays `in_progress`; re-run `complete` resumes from upload without a second reply; second `inbox` returns 0 items (SC-005); `skip --reason duplicate` posts the §3 reply + ✅; `skip --reason expired` does nothing, with `--mark-done --deadline 2026-10-20` posts §4 (with that date) + ✅, and `--mark-done` without `--deadline` → exit 2; `inbox --limit 2` where the older item fails to fetch → only 1 item returned, no replacement pulled in (FR-003)

### Implementation for User Story 3

- [ ] T056 [P] [US3] Implement `agents/job-apply/src/job_apply/slack_api.py` (httpx client, `shared.retry`, bot user id via `auth.test`, no token in logs)
- [ ] T057 [US3] Implement `agents/job-apply/src/job_apply/inbox.py` (state computation, posting detection, selection, caching to `.job-state/inbox/`, uses `fetch.py` for `new` messages with links)
- [ ] T058 [P] [US3] Implement `agents/job-apply/src/job_apply/report.py` (message texts, `complete` step resume via `meta.slack`)
- [ ] T059 [US3] Wire `inbox`, `skip` (with `--deadline`), and Slack branch of `complete` in `agents/job-apply/src/job_apply/cli.py`; `init` accepts Slack ids from the inbox cache
- [ ] T060 [US3] Create `.claude/commands/job-run.md` per contracts/slash-commands.md (`argument-hint: [개수]`; doctor → inbox → extract → 처리 전 목록 in the documented format → ask about 미상 names, expired (이번만 건너뛰기 / 건너뛰고 ✅로 정리 → `skip --reason expired --deadline <추출한 마감일> --mark-done` / 처리), duplicates (새로 만들기 / 건너뛰기), go/no-go → skip/process → final per-posting summary; same 공고별 처리 and 규칙 as `/tailor`)
- [ ] T061 [US3] Add `Bash(agents/job-apply/bin/job inbox:*)` and `Bash(agents/job-apply/bin/job skip:*)` to `.claude/settings.json`

**Checkpoint**: US3 — Slack에 모아 둔 공고가 `/job-run`으로 처리되고 ✅가 달린다.

---

## Phase 6: User Story 4 - 공고를 가져오지 못했을 때 본문 요청하기 (Priority: P3)

**Goal**: 가져오기 실패 → ❓ + 요청 답글 → 사용자가 스레드에 본문 → 다음 실행에서 처리. 같은 요청은 반복하지 않는다.

**Independent Test**: 실패 링크 메시지 하나와 정상 메시지 하나로 `inbox`를 실행하면, 실패 쪽에만 ❓와 §2 답글이 달리고 정상 쪽은 대상에 남는다. 스레드에 사용자 답글을 추가하고 다시 `inbox`를 실행하면 `body_provided`로 대상이 된다. 답글 없이 다시 실행하면 `awaiting_body`이고 추가 요청은 없다.

### Tests for User Story 4

- [ ] T062 [P] [US4] Extend `agents/job-apply/tests/test_inbox.py`: fetch failure → `reactions.add(question)` + §2 reply with the reason, item moved to `requested_now`, other items still processed (SC-006); message with `question` and no non-bot replies → `awaiting_body`, no Slack write; with user replies → `body_provided`, body = user replies joined in order, bot replies (`bot_id` or bot user id) ignored
- [ ] T063 [P] [US4] Extend `agents/job-apply/tests/test_flow_job_run.py`: `body_provided` posting processes end to end and gets ✅ (its `fetch` is `skipped`, `url_key` still from the original link for dedup)

### Implementation for User Story 4

- [ ] T064 [US4] Implement the ❓ request and thread-body logic in `agents/job-apply/src/job_apply/inbox.py` and the §2 text in `agents/job-apply/src/job_apply/report.py`
- [ ] T065 [US4] Update `.claude/commands/job-run.md` list output for "본문 대기" and "이번에 본문 요청", and `.claude/commands/tailor.md` step 3 (ask for the body in the terminal on `fetch=failed`)

**Checkpoint**: US4 — 막힌 공고도 사람 손을 조금만 빌려 처리된다.

---

## Phase 7: User Story 5 - 원본을 새 버전으로 바꾸기 (Priority: P3)

**Goal**: 원본을 바꾼 뒤 만드는 폴더는 새 원본을 쓰고, 이전 폴더는 그대로다. 처리 중 원본이 바뀌면 실패로 알린다.

**Independent Test**: 공고 A 처리 → `private/resume.pdf` 교체 → 공고 B를 처리하면 두 폴더의 `base/` 해시와 `changes.md` 원본 해시가 서로 다르다. A 폴더의 파일은 바이트 단위로 그대로다.

- [ ] T066 [P] [US5] Write the test in `agents/job-apply/tests/test_flow_sources.py`: scenario above; plus replacing `private/portfolio.pptx` between `init` and `apply` → `apply` still uses `base/portfolio.pptx` and succeeds, the folder's `meta.sources` unchanged (FR-008, FR-009); and a fake that changes `private/resume.pdf` while a single command runs (inside `sources.guard()`) → exit 8 "원본이 처리 중에 바뀜", folder `failed` (data-model §1)
- [ ] T067 [US5] Make `init` record `meta.sources` (sha256 + mtime) and `apply`/`complete` compare `base/` copies only (never re-read `private/` after `init`) in `agents/job-apply/src/job_apply/cli.py`; `sources.guard()` stays per command; fix anything the T066 test exposes

**Checkpoint**: 모든 사용자 스토리 완료.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T068 [P] Write `agents/job-apply/README.md`: 준비(LibreOffice, 글꼴, Slack 앱 권한 `channels:history`/`groups:history`, `reactions:read`, `reactions:write`, `chat:write`, `files:write`, `.env`, `config/job.yaml`), 명령(`/job-run`, `/tailor`), 폴더 구조, 개인정보 주의, 제출은 직접
- [ ] T069 [P] Update root `README.md` agent table: job-apply 설명 "Slack #job-apply 공고로 맞춤 이력서·포트폴리오 준비(제출은 직접)", 상태 "구현 완료"
- [ ] T070 [P] Add `agents/job-apply/tests/test_privacy.py` that runs `git check-ignore` on `agents/job-apply/private/x`, `applications/x`, `.job-state/x` in the real repo (not the tmp `job_root`) and asserts all are ignored (FR-024)
- [ ] T071 Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` from the repo root and from `agents/job-apply/`; fix failures
- [ ] T072 Run `JOB_RENDER=1 uv run pytest agents/job-apply -m render` locally (LibreOffice 26.8.1 installed) and fix failures
- [ ] T073 Walk through `specs/003-job-tailor-applications/quickstart.md` sections 0–5 with the user's real originals and a Slack test channel; record outcomes, per-posting processing time excluding confirmation waits (SC-003, ≤ 10분), and any spec gaps in `specs/003-job-tailor-applications/quickstart.md` under a "검증 기록" heading (no personal data)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 의존 없음. T002는 T001 뒤에 한다(워크스페이스 멤버가 있어야 `uv lock` 가능).
- **Foundational (Phase 2)**: Setup 뒤에 한다. 모든 스토리를 막는다.
- **US1 (Phase 3)**: Foundational 뒤에 한다. MVP다.
- **US2 (Phase 4)**: US1의 `apply`(T036, T040) 위에 얹는다.
- **US3 (Phase 5)**: US1의 `fetch`·`init`·`verify`·`complete`(T033, T040)가 필요하다. US2와는 독립이라 병렬로 진행할 수 있다.
- **US4 (Phase 6)**: US3의 `inbox`·`slack_api`가 필요하다.
- **US5 (Phase 7)**: US1 뒤에 언제든 할 수 있다.
- **Polish (Phase 8)**: 원하는 스토리가 끝난 뒤에 한다.

### Within Each User Story

- 테스트를 먼저 쓰고 실패를 확인한다 → 모듈 구현 → CLI 연결 → 슬래시 명령·설정.

### Parallel Opportunities

- Setup: T003–T008은 서로 다른 파일이다.
- Foundational: T009, T010, T011이 병렬이다. 각 모듈의 test/impl 쌍(T013/14, T015/16, T017/18, T019/20, T021/22)은 서로 독립이다.
- US1: T025–T031(테스트 7개)이 병렬이다. T033–T035, T037–T039(구현)도 병렬이다.
- US2와 US3은 서로 다른 개발 흐름으로 동시에 진행할 수 있다.

## Parallel Example: User Story 1

```bash
# 테스트 먼저 (모두 다른 파일)
Task: "T025 test_fetch.py"     Task: "T026 test_dedup.py"     Task: "T027 test_pptx_dump.py"
Task: "T028 test_pptx_apply.py" Task: "T029 test_resume_pdf.py" Task: "T030 test_changes.py"
Task: "T031 test_verify.py"

# 구현 (서로 다른 모듈)
Task: "T033 fetch.py"  Task: "T034 dedup.py"  Task: "T035 pptx_dump.py"
Task: "T037 resume_pdf.py"  Task: "T038 changes.py"  Task: "T039 verify.py"
```

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 → Phase 2 → Phase 3
2. **멈추고 검증**: `/tailor`를 실제 공개 공고 하나로 실행해 quickstart §2 확인
3. 이 시점에 이미 공고 하나당 맞춤 자료를 만들 수 있다(Slack 없이)

### Incremental Delivery

1. US1(MVP) → US2(포트폴리오 품질) → 실사용 시작
2. US3(Slack 일괄) → US4(❓ 흐름) → US5(원본 교체 검증)
3. 스토리마다 `uv run pytest`가 통과한 상태로 커밋한다

## Notes

- 커밋은 스토리 단위로, 사용자 확인 후 한다. `applications/`, `private/`, `.env`는 절대 스테이징하지 않는다.
- 세션이 쓰는 산출물(job.md 본문, analysis.md, resume.md, tailor.json)은 테스트에서 픽스처로 대체한다. 모델 품질은 quickstart 수동 검증(T073)으로 확인한다.
