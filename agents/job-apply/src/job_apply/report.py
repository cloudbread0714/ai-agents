"""#job-apply thread replies (contracts/slack-message.md). All user text is mrkdwn-escaped."""

from __future__ import annotations

from datetime import date

from job_apply.changes import KIND_LABEL
from job_apply.folders import clean
from job_apply.models import Meta
from job_apply.verify import section
from shared.slack import escape_mrkdwn

LOW_FIT = 40


def fit_line(score: int | None, summary: str | None) -> str:
    if score is None:
        return "미상"
    prefix = "⚠️ 낮은 적합도 " if score < LOW_FIT else ""
    tail = f" — {escape_mrkdwn(summary)}" if summary else ""
    return f"{prefix}{score}/100{tail}"


def deadline_line(deadline: date | None, today: date) -> str:
    if deadline is None:
        return "상시·미상"
    days = (deadline - today).days
    dday = "D-day" if days == 0 else (f"D-{days}" if days > 0 else f"D+{-days}")
    return f"{deadline.isoformat()} ({dday})"


def render_line(meta: Meta) -> str:
    issues = meta.render.remaining_issues
    if not issues:
        return "문제 없음"
    shown = ", ".join(f"슬라이드 {i.slide}: {KIND_LABEL[i.kind]}" for i in issues[:3])
    return f"⚠️ 남은 문제 {len(issues)}건 ({shown})"


def summary_lines(job_md: str) -> list[str]:
    lines = [ln.strip().lstrip("-*• ").strip() for ln in section(job_md, "## 요약").splitlines()]
    return [ln for ln in lines if ln][:3]


def completion(meta: Meta, job_md: str, folder: str, summary: str | None, today: date) -> str:
    p = meta.posting
    out = [
        f"✅ 지원 자료 준비 완료 — {escape_mrkdwn(p.company)} · {escape_mrkdwn(p.role)}",
        f"• 마감: {deadline_line(p.deadline, today)}",
        f"• 적합도: {fit_line(meta.fit_score, summary)}",
    ]
    lines = summary_lines(job_md)
    if lines:
        out.append("• 공고 요약:")
        out += [f"    – {escape_mrkdwn(ln)}" for ln in lines]
    out += [f"• 폴더: {folder}", f"• 렌더링: {render_line(meta)}"]
    if p.extra_urls:
        out.append("• 처리하지 않은 링크: " + " ".join(p.extra_urls))
    out.append("제출은 직접 해 주세요.")
    return "\n".join(out)


def body_request(reason: str) -> str:
    return (
        f"❓ 공고 페이지를 가져오지 못했어요 (사유: {escape_mrkdwn(reason)}).\n"
        "이 스레드에 공고 본문을 붙여 주시면 다음 /job-run 때 처리할게요."
    )


def duplicate(folder: str, fit_score: int | None) -> str:
    fit = f" (적합도 {fit_score}/100)" if fit_score is not None else ""
    return f"🔁 이미 처리한 공고예요 → {folder}{fit}"


def expired(deadline: date) -> str:
    return f"⏰ 마감({deadline.isoformat()})이 지나 처리하지 않았어요."


def file_names(company: str, role: str) -> tuple[str, str]:
    stem = f"{clean(company)}_{clean(role)}"
    return f"{stem}_resume.pdf", f"{stem}_portfolio.pdf"
