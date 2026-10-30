"""Stand-ins for what the Claude Code session writes into a folder (job.md sections,
analysis.md, tailor.json). Contents are fictional and grounded in the samples."""

from __future__ import annotations

import copy
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

RESUME_EDITS = [
    {
        "paragraph": 4,
        "text": "Python FastAPI 기반 API 서버 설계·운영",
        "source": "resume.txt:L5",
        "reason": "공고 주요 업무에 맞춰 다듬음",
    }
]
RESUME_ROW_ORDER = [{"table": 1, "order": [0, 2, 1, 3], "reason": "PostgreSQL 항목을 위로"}]


def plan(edits=None, order=None, acknowledged=None, resume_edits=None, row_order=None) -> dict:
    return {
        "schema": 2,
        "acknowledged_warnings": acknowledged or [],
        "resume": {
            "edits": copy.deepcopy(RESUME_EDITS if resume_edits is None else resume_edits),
            "row_order": copy.deepcopy(RESUME_ROW_ORDER if row_order is None else row_order),
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
    """``extra``: "- line" items added to the resume after its last 경력 row (paragraph 6)."""
    job = folder / "job.md"
    job.write_text(job.read_text(encoding="utf-8") + JOB_SECTIONS, encoding="utf-8")
    (folder / "analysis.md").write_text(ANALYSIS.format(score=score), encoding="utf-8")
    added = [
        {
            "paragraph": 6,
            "op": {"kind": "insert_after", "text": line.removeprefix("- ")},
            "source": "resume.txt:L7",
            "reason": "테스트용 추가 문장",
        }
        for line in extra.splitlines()
        if line.strip()
    ]
    write_plan(folder, tailor or plan(resume_edits=[*RESUME_EDITS, *added]))


def write_plan(folder: Path, data: dict) -> None:
    (folder / "tailor.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
