"""Stand-ins for what the Claude Code session writes into a folder (job.md sections,
analysis.md, resume.md, tailor.json). Contents are fictional and grounded in the samples."""

from __future__ import annotations

import json
from pathlib import Path

JOB_SECTIONS = """
## 요약
- Python 백엔드 API 개발
- PostgreSQL·Docker 경험 필요
- Kubernetes 우대

## 자격 요건
- Python 3년 이상

## 우대 사항
- Kubernetes 운영

## 주요 업무
- API 서버 개발

## 기타(근무지·형태·전형)
- 서울, 정규직
"""

ANALYSIS = """---
fit_score: {score}
summary: "Python·PostgreSQL 일치, Kubernetes 경험 부족"
---
## 적합도 근거
필수 요건 3개 중 3개 충족.

## 일치하는 점
- Python, PostgreSQL, Docker

## 부족한 점
- Kubernetes 운영 경험

## 지원 전 보완 제안
- 쿠버네티스 학습 정리
"""

RESUME = """# 홍길동

백엔드 개발자 · hong@example.com

## 경력

### 가상테크 (2021-2024)
- Python FastAPI 기반 API 서버 설계와 운영
- PostgreSQL 쿼리 튜닝으로 응답 시간 30% 개선
- Docker 배포 파이프라인 구축
{extra}
## 기술

Python, FastAPI, PostgreSQL, Docker, AWS
"""


def plan(edits=None, order=None, acknowledged=None) -> dict:
    return {
        "schema": 1,
        "acknowledged_warnings": acknowledged or [],
        "resume": {
            "changes": [
                {
                    "section": "경력",
                    "before": "",
                    "after": "PostgreSQL 쿼리 튜닝 항목을 위로",
                    "source": "resume.txt:L6",
                    "reason": "공고 자격 요건과 맞춤",
                }
            ]
        },
        "portfolio": {
            "slide_order": order or [1, 2, 3, 4, 5],
            "edits": edits
            if edits is not None
            else [
                {
                    "slide": 2,
                    "shape_id": 2,
                    "paragraph": 0,
                    "runs": ["핵심 역량: ", "Python API 서버"],
                    "source": "portfolio.json:s2/sh2/p0",
                    "reason": "공고 주요 업무에 맞춤",
                }
            ],
        },
    }


def write(folder: Path, *, score: int = 72, extra: str = "", tailor: dict | None = None) -> None:
    job = folder / "job.md"
    job.write_text(job.read_text(encoding="utf-8") + JOB_SECTIONS, encoding="utf-8")
    (folder / "analysis.md").write_text(ANALYSIS.format(score=score), encoding="utf-8")
    (folder / "resume.md").write_text(RESUME.format(extra=extra), encoding="utf-8")
    write_plan(folder, tailor or plan())


def write_plan(folder: Path, data: dict) -> None:
    (folder / "tailor.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
