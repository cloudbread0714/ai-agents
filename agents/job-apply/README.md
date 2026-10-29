# job-apply

채용 공고 하나마다 맞춤 이력서·포트폴리오를 준비하는 에이전트입니다. **지원서 제출은 직접 합니다.**
스펙: [`specs/003-job-tailor-applications/`](../../specs/003-job-tailor-applications/spec.md)

- 판단(공고 요건 추출, 적합도 분석, 이력서 작성, 포트폴리오 문구 계획, 미리보기 확인)은 Claude Code 세션이 합니다.
- `job` CLI는 결정적인 일만 합니다. Slack 읽기·반응·답글·파일 올리기, 공고 가져오기, 폴더와 원본 사본, PPTX 적용과 디자인 보존 검사, 렌더링과 넘침 검출, 이력서 PDF, 근거 검사, 중복 확인이에요.
- 둘은 편집 계획 파일 `tailor.json` 으로 주고받습니다. 모든 변경 항목에 원본 근거 위치(`source`)와 이유(`reason`)가 있어야 해요.

## 준비

1. **원본**: `agents/job-apply/private/resume.pdf`, `agents/job-apply/private/portfolio.pptx` 를 넣습니다. 이 폴더는 git이 무시하고, CLI는 읽기만 합니다.
2. **LibreOffice**: `brew install --cask libreoffice` (포트폴리오 PDF 렌더링). 포트폴리오가 쓰는 글꼴도 설치해 두세요. 없으면 줄 바꿈이 달라질 수 있어요.
3. **이력서 글꼴**(선택): `config/job.yaml` 의 `resume.font_files` 중 처음 찾은 파일을 씁니다(Pretendard → Noto Sans KR → AppleSDGothicNeo). 없으면 PyMuPDF 내장 CJK 글꼴을 써요.
4. **Slack**(`/job-run` 에만 필요):
   - Slack 앱 봇 권한: `channels:history`(비공개 채널이면 `groups:history`), `reactions:read`, `reactions:write`, `chat:write`, `files:write`
   - 봇을 #job-apply 에 초대합니다.
   - `.env.example` 을 `.env` 로 복사해 `SLACK_BOT_TOKEN` 을 채웁니다. 채널 ID는 `config/job.yaml` 의 `slack.channel_id` 나 `.env` 의 `SLACK_JOB_CHANNEL_ID` 에 둡니다. `bin/job` 이 `.env` 를 자동으로 읽어요(셸에 이미 있는 값이 우선).
5. 확인: `agents/job-apply/bin/job doctor`

## 명령

| 명령 | 하는 일 |
|------|---------|
| `/job-run [개수]` | #job-apply 에서 ✅ 없는 공고를 오래된 순으로 모아, 처리 전 목록을 확인받고 하나씩 처리합니다. 끝나면 스레드에 요약 답글, PDF 2개, ✅를 남겨요 |
| `/tailor <링크 또는 본문>` | 공고 하나를 바로 처리합니다. 결과는 터미널에만 알려요 |

- 공고 페이지를 가져오지 못하면 `/job-run` 은 그 메시지에 ❓와 본문 요청 답글을 남깁니다. 스레드에 본문을 붙여 두면 다음 실행 때 처리해요.
- 메시지에 직접 ✅를 달면 대상에서 빠집니다.
- 같은 공고(URL, 추적 파라미터 무시)를 이미 처리했으면 알려 주고, 새로 만들지 건너뛸지 묻습니다.

CLI 서브커맨드(`doctor`, `inbox`, `fetch`, `init`, `resume-pdf`, `apply`, `note-issue`, `verify`, `complete`, `skip`, `fail`, `status`)는 [contracts/cli.md](../../specs/003-job-tailor-applications/contracts/cli.md)에 있습니다.

## 폴더 구조

```text
agents/job-apply/
├── private/                       # 원본 (git 무시, 읽기 전용)
├── applications/                  # 결과물 (git 무시)
│   └── 2026-10-27_예시회사_백엔드-개발자/
│       ├── meta.json              # 상태(in_progress/done/failed), 원본 해시, 렌더링·Slack 진행
│       ├── base/                  # 원본 사본, resume.txt, portfolio.json, render/
│       ├── job.md  analysis.md  tailor.json  resume.md
│       ├── resume.pdf  portfolio.pptx  portfolio.pdf  preview/slide-NN.png
│       └── changes.md             # 변경 내역과 근거 (자동 생성)
├── .job-state/                    # 수집 캐시, LibreOffice 프로필, 로그 (git 무시)
└── config/job.yaml                # 채널 ID, 글꼴, 가져오기·렌더링 설정 (비밀값 없음)
```

## 지키는 것

- 원본 이력서·포트폴리오는 바꾸지 않습니다. 명령마다 원본 해시를 확인하고, 처리 중에 바뀌면 그 공고를 실패로 처리해요.
- 원본에 없는 경력·기술·수치를 만들지 않습니다. `job verify` 가 원본에 없는 숫자·영문 기술명·부족한 요건 키워드를 찾아내고, 해명되지 않은 경고가 남으면 완료되지 않아요.
- 포트폴리오는 문구와 슬라이드 순서만 바꿉니다. 도형·위치·크기·글꼴·색·이미지·레이아웃이 바뀌면 적용을 거부해요(exit 4). 넘침은 문구를 줄여 해결하고, 최대 3회 다시 시도합니다.
- 개인정보 파일은 커밋하지 않습니다. `doctor` 가 `private/`, `applications/`, `.job-state/` 가 git에서 무시되는지 확인해요.
- 제출·로그인·폼 입력은 하지 않습니다.

## 테스트

```bash
uv run pytest agents/job-apply                          # 네트워크·LibreOffice 없이
JOB_RENDER=1 uv run pytest agents/job-apply -m render   # 실제 LibreOffice 렌더링
```

테스트 데이터는 모두 가상 인물(홍길동)과 가상 회사입니다.
