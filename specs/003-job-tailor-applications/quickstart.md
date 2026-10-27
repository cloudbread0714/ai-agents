# Quickstart: job-apply 검증 가이드

이 기능이 처음부터 끝까지 동작하는지 확인하는 순서다. 세부 형식은 [contracts/](./contracts/)와 [data-model.md](./data-model.md)를 참고한다.

## 0. 준비 (한 번만)

```bash
brew install --cask libreoffice          # PPTX → PDF 렌더링 (research R4)
uv sync                                   # 레포 루트
```

- `agents/job-apply/private/`에 `resume.pdf`, `portfolio.pptx`를 넣는다(커밋되지 않음).
- 포트폴리오가 쓰는 글꼴을 설치한다(`job doctor`가 빠진 글꼴을 알려 줌).
- Slack 앱을 만든다.
  - 권한: `channels:history`(비공개면 `groups:history`), `reactions:read`, `reactions:write`, `chat:write`, `files:write`
  - 앱을 #job-apply에 초대한다.
- `agents/job-apply/.env`에 다음을 넣는다.
  ```
  SLACK_BOT_TOKEN=xoxb-…
  ```
  `ANTHROPIC_API_KEY`는 필요 없다(research R1).
- `agents/job-apply/config/job.yaml`에 `slack.channel_id`를 적는다.

```bash
agents/job-apply/bin/job doctor          # 모든 항목 ✅, slack_ready=true
```

## 1. 자동 테스트 (네트워크·LibreOffice 없이)

```bash
uv run pytest agents/job-apply           # 기본: 모킹된 Slack·웹, 고정 렌더링 픽스처
uv run ruff check agents/job-apply
```

**기대 결과**:
- 원본 불변(SC-001)
- 디자인 보존 위반 검출(exit 4)
- 넘침 검출과 base 문제 제외
- 중복·❓·✅ 상태 계산
- 완료 보고 단계 재개

위 항목의 테스트가 모두 통과한다.

```bash
JOB_RENDER=1 uv run pytest agents/job-apply -m render   # 실제 LibreOffice 렌더링
```

**기대 결과**: 샘플 PPTX에서 일부러 긴 문구를 넣은 슬라이드가 `overflow`로 잡히고, 원본에 원래 있던 겹침은 보고되지 않는다.

## 2. `/tailor` 수동 검증 (US1, US2)

1. Claude Code에서 `/tailor <공개 채용 공고 링크>`를 실행한다.
2. 회사·직무·마감일 확인 → 진행.
3. 확인할 것:
   - `applications/<오늘>_<회사>_<직무>/`에 FR-010 산출물이 모두 있다.
   - `shasum private/*`가 실행 전과 같다(SC-001).
   - `changes.md`의 모든 변경에 근거와 이유가 있고, 근거 검사 경고가 0건이거나 설명이 붙어 있다(SC-002).
   - `preview/` 이미지와 `portfolio.pdf`에서 글자 넘침이 없거나, 남은 문제가 `changes.md`에 적혀 있다(SC-004).
   - `portfolio.pptx`를 PowerPoint로 열면 원본과 디자인이 같고 문구·순서만 다르다.
   - 걸린 시간이 확인 대기 시간을 빼고 10분 이내다(SC-003).
4. 본문 붙여 넣기: `/tailor <공고 본문 전체>` → 같은 산출물이 나온다.

## 3. `/job-run` 수동 검증 (US3, US4)

#job-apply에 다음을 올린다.
- (a) 공개 공고 링크 2개
- (b) 로그인이 필요한 공고 링크 1개
- (c) "나중에 볼 것" 같은 잡담 1개
- 그리고 (a) 중 하나에 미리 ✅를 단다.

1. `/job-run` 실행 → 목록 확인.
   - 확인할 것: ✅ 달린 공고는 목록에 없다. (b)는 ❓ 반응과 본문 요청 답글이 달리고 "이번에 본문 요청"으로 나온다. (c)는 "공고가 아닌 메시지 1건 제외"로 나온다.
2. 진행 → 남은 (a) 1건의 스레드에 완료 보고, PDF 2개, ✅가 달린다.
3. `/job-run`을 다시 실행한다.
   - 확인할 것: 처리할 공고 0건, (b)는 "본문 대기"로 나오고 답글이 또 달리지 않는다(SC-005, FR-018).
4. (b) 스레드에 공고 본문을 붙이고 `/job-run`을 실행한다.
   - 확인할 것: (b)가 처리되고 ✅가 달린다.
5. 처리한 (a)의 링크를 utm 파라미터를 붙여 새 메시지로 올리고 `/job-run`을 실행한다.
   - 확인할 것: "🔁 이미 처리됨"으로 나온다. 건너뛰기를 고르면 기존 폴더 답글과 ✅가 달린다(FR-016).
6. `/job-run 1`을 실행한다(대상 2건 이상일 때).
   - 확인할 것: 가장 오래된 1건만 처리된다.

## 4. 원본 교체 (US5)

1. `private/resume.pdf`를 다른 버전으로 바꾸고 새 공고를 `/tailor`로 처리한다.
2. 확인할 것: 새 폴더의 `base/resume.pdf`와 `changes.md`의 원본 해시는 새 버전이고, 이전 폴더는 바뀌지 않았다.

## 5. 실패 복구

- `soffice`를 PATH에서 빼고 `/tailor`를 실행한다 → `doctor`가 멈추고 설치를 안내한다.
- 완료 보고 중 Slack을 끊는다(토큰을 잘못 바꿈) → 공고에 ✅가 없고 `meta.status`는 `in_progress`다.
  토큰을 고친 뒤 `/job-run`을 다시 실행하면 같은 폴더에서 빠진 보고 단계부터 이어서 한다(FR-019, FR-020).
