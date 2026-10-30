"""``job`` CLI (contracts/cli.md). Human-readable lines on stdout, then a final
``JOB_RESULT {json}`` line for the slash commands. Every subcommand runs inside
``sources.guard()``, so an original that changes mid-command ends it with exit 8."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import IO, Any
from zoneinfo import ZoneInfo

import httpx

from job_apply import (
    changes,
    dedup,
    design_guard,
    doctor,
    folders,
    inbox,
    layout_check,
    pptx_apply,
    pptx_dump,
    report,
    resume_pdf,
    sources,
    verify,
)
from job_apply import fetch as fetch_mod
from job_apply.config import AGENT_ROOT, JobConfig, Paths, load_config, slack_channel, slack_token
from job_apply.errors import (
    DuplicatePosting,
    JobError,
    SlackError,
    SourceChangedError,
    UnresolvedWarnings,
    UsageError,
)
from job_apply.models import FetchInfo, Meta, MetaError, Posting, PostingRef, RenderIssue, load_plan
from job_apply.render import Renderer, SofficeRenderer, render_previews
from shared.logging import JsonFormatter, SecretMaskingFilter, get_logger
from shared.slack import SlackApiError, add_reaction, post_message, upload_files

KST = ZoneInfo("Asia/Seoul")
log = get_logger(__name__)


@dataclass
class Ctx:
    paths: Paths
    environ: Mapping[str, str]
    http: httpx.Client
    now: datetime
    out: IO[str]
    renderer: Renderer | None
    run: Callable[..., subprocess.CompletedProcess]
    which: Callable[[str], str | None]
    base_delay: float
    folder: Path | None = None
    _cfg: JobConfig | None = field(default=None, repr=False)

    @property
    def cfg(self) -> JobConfig:
        if self._cfg is None:
            self._cfg = load_config(self.paths)
        return self._cfg

    @property
    def today(self) -> date:
        return self.now.astimezone(KST).date()

    @property
    def slack_kw(self) -> dict[str, Any]:
        return {"client": self.http, "base_delay": self.base_delay}

    def render(self) -> Renderer:
        if self.renderer is None:
            self.renderer = SofficeRenderer(
                self.paths.lo_profile,
                timeout_s=self.cfg.render.timeout_s,
                run=self.run,
                which=self.which,
            )
        return self.renderer

    def say(self, *lines: str) -> None:
        for line in lines:
            self.out.write(line.rstrip() + "\n")


# --- argument parsing -------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="job", description="job-apply: 공고별 맞춤 지원 자료 준비")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="원본·LibreOffice·글꼴·gitignore·Slack 준비 확인")
    ib = sub.add_parser("inbox", help="#job-apply에서 처리할 공고 수집")
    ib.add_argument("--limit", type=int)
    fe = sub.add_parser("fetch", help="/tailor용 공고 가져오기")
    src = fe.add_mutually_exclusive_group(required=True)
    src.add_argument("url", nargs="?")
    src.add_argument("--text-file", type=Path)
    it = sub.add_parser("init", help="지원 폴더 만들기")
    it.add_argument("id")
    it.add_argument("--company", required=True)
    it.add_argument("--role", required=True)
    it.add_argument("--deadline", type=date.fromisoformat)
    it.add_argument("--new", action="store_true")
    for name, help_ in (
        ("apply", "tailor.json 포트폴리오 적용과 렌더링 점검"),
        ("resume-pdf", "resume.md → resume.pdf"),
        ("verify", "산출물·형식·근거 검사"),
        ("complete", "완료 처리(Slack 공고면 답글·PDF·✅)"),
    ):
        sub.add_parser(name, help=help_).add_argument("folder")
    ni = sub.add_parser("note-issue", help="미리보기에서 찾은 문제 기록")
    ni.add_argument("folder")
    ni.add_argument("--slide", type=int, required=True)
    ni.add_argument("--detail", required=True)
    sk = sub.add_parser("skip", help="중복·마감 공고 건너뛰기")
    sk.add_argument("id")
    sk.add_argument("--reason", choices=["duplicate", "expired"], required=True)
    sk.add_argument("--deadline", type=date.fromisoformat)
    sk.add_argument("--mark-done", action="store_true")
    fa = sub.add_parser("fail", help="세션 단계 실패 기록")
    fa.add_argument("folder")
    fa.add_argument("--step", required=True)
    fa.add_argument("--reason", required=True)
    st = sub.add_parser("status", help="지원 폴더 목록")
    st.add_argument("--all", action="store_true")
    return p


# --- helpers ----------------------------------------------------------------------------


def _folder(ctx: Ctx, arg: str) -> Path:
    candidates = (
        [Path(arg)]
        if Path(arg).is_absolute()
        else [
            ctx.paths.root.parents[1] / arg,
            ctx.paths.applications / arg,
            Path.cwd() / arg,
        ]
    )
    for c in candidates:
        if (c / "meta.json").is_file():
            ctx.folder = c.resolve()
            return ctx.folder
    raise UsageError(f"지원 폴더를 찾을 수 없어요: {arg}")


def _meta(folder: Path, *, editable: bool = True) -> Meta:
    meta = folders.read_meta(folder)
    if editable and meta.status == "done":
        raise UsageError("완료된 폴더는 다시 고치지 않아요. 새로 만들려면 init --new를 쓰세요")
    return meta


def _base_dump(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "base" / "portfolio.json").read_text(encoding="utf-8"))


def _plan_or_none(folder: Path):
    try:
        return load_plan(folder / "tailor.json", _base_dump(folder)["slide_count"])
    except (JobError, OSError, KeyError):
        return None


def _direct_id(key: str) -> str:
    return "t-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


# --- commands ---------------------------------------------------------------------------


def cmd_doctor(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    rep = doctor.run_checks(
        ctx.paths,
        ctx.cfg,
        ctx.environ,
        run=ctx.run,
        which=ctx.which,
        slack_kw=ctx.slack_kw,
        repo_root=ctx.paths.root.parents[1],
    )
    ctx.say(*rep.lines)
    return (0 if not rep.missing else 5), rep.result()


def cmd_inbox(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    token, channel = slack_token(ctx.environ), slack_channel(ctx.cfg, ctx.environ)
    try:
        result = inbox.collect(
            ctx.paths,
            token,
            channel,
            args.limit,
            lambda url: fetch_mod.fetch(url, ctx.cfg.fetch, ctx.http, base_delay=ctx.base_delay),
            ctx.slack_kw,
        )
    except SlackApiError as exc:
        raise SlackError(f"Slack 오류: {exc}") from None
    ctx.say(
        f"처리 대상 {len(result.items)}건",
        f"본문 대기 {len(result.awaiting_body)}건",
        f"이번에 본문 요청 {len(result.requested_now)}건",
        f"공고가 아닌 메시지 {result.excluded_non_posting}건 제외",
    )
    return 0, inbox.to_json(result)


def cmd_fetch(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    if args.text_file is not None:
        text = args.text_file.read_text(encoding="utf-8")
        url, key, got = None, dedup.text_key(text), FetchInfo(status="skipped")
    else:
        url = args.url
        key = dedup.url_key(url)
        res = fetch_mod.fetch(url, ctx.cfg.fetch, ctx.http, base_delay=ctx.base_delay)
        text, got = res.text, FetchInfo(status=res.status, reason=res.reason)
    done = dedup.find_done(ctx.paths.applications, key)
    posting_id = _direct_id(key)
    image_paths: list[str] = []
    if got.status == "images":
        image_paths = inbox.save_images(ctx.paths, posting_id, res.images)
        if not image_paths:
            got = FetchInfo(status="failed", reason="본문 이미지를 열지 못함")
    posting = Posting(
        id=posting_id,
        origin="direct",
        url=url,
        url_key=key,
        fetch=got,
        duplicate_of=ctx.paths.rel(done) if done else None,
    )
    text_path = inbox.save_posting(ctx.paths, posting, text)
    if got.status == "failed":
        ctx.say(f"공고를 가져오지 못했어요: {got.reason}")
    elif got.status == "images":
        ctx.say(f"공고 본문이 이미지예요. {len(image_paths)}장으로 저장했어요")
    else:
        ctx.say(f"공고 본문을 저장했어요: {ctx.paths.rel(text_path)}")
    return 0, {
        "id": posting.id,
        "fetch": got.status,
        "reason": got.reason,
        "duplicate_of": posting.duplicate_of,
        "text_path": ctx.paths.rel(text_path),
        "images": image_paths,
    }


def _job_header(posting: Posting, company: str, role: str, deadline: date | None, text: str) -> str:
    lines = [f"# {company} · {role}", ""]
    lines.append(f"- 원문: {posting.url}" if posting.url else "- 원문: (본문 직접 입력)")
    lines.append(f"- 마감: {deadline.isoformat() if deadline else '상시·미상'}")
    lines += [
        "",
        "<details><summary>원문 본문</summary>",
        "",
        "```text",
        text.strip(),
        "```",
        "",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def cmd_init(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    paths = ctx.paths
    try:
        posting, text = inbox.load_posting(paths, args.id)
    except FileNotFoundError:
        raise UsageError(
            f"수집한 공고가 없어요: {args.id} (job fetch 또는 job inbox 먼저)"
        ) from None
    done = dedup.find_done(paths.applications, posting.url_key)
    if done and not args.new:
        raise DuplicatePosting(paths.rel(done))
    sources.check(paths)
    folder = folders.find_resumable(paths.applications, posting.id, posting.url_key)
    reused = folder is not None
    if folder is None:
        folder = folders.new_folder(paths.applications, ctx.today, args.company, args.role)
    ctx.folder = folder
    base = folder / "base"
    sources.copy_to_base(paths, base)
    ref = PostingRef(
        id=posting.id,
        origin=posting.origin,
        message_ts=posting.message_ts,
        url=posting.url,
        extra_urls=posting.extra_urls,
        url_key=posting.url_key,
        company=args.company,
        role=args.role,
        deadline=args.deadline,
    )
    snapshot = sources.of_copies(paths, base)
    if reused:
        meta = folders.read_meta(folder)
        meta.move("in_progress")
        meta.posting, meta.sources, meta.error = ref, snapshot, None
        meta.render.attempts, meta.render.remaining_issues = 0, []
    else:
        meta = Meta(
            status="in_progress", created_at=ctx.now.astimezone(KST), posting=ref, sources=snapshot
        )
    # Written before the slow steps, so a failure below (exit 8 included) can mark it failed.
    folders.write_meta(folder, meta)

    sources.extract_resume_text(base / "resume.pdf", base / "resume.txt")
    pptx_dump.dump_file(base / "portfolio.pptx", base / "portfolio.json")
    pdf = ctx.render().to_pdf(base / "portfolio.pptx", base / "render")
    slide_count = _base_dump(folder)["slide_count"]
    render_previews(pdf, range(1, slide_count + 1), base / "render", ctx.cfg.render.preview_dpi)

    posting.company, posting.role, posting.deadline = args.company, args.role, args.deadline
    inbox.save_posting(paths, posting, text)
    (folder / "job.md").write_text(
        _job_header(posting, args.company, args.role, args.deadline, text), encoding="utf-8"
    )
    rel = paths.rel(folder)
    ctx.say(f"지원 폴더를 {'다시 쓰고' if reused else '만들었'}어요: {rel}")
    return 0, {"folder": rel, "reused": reused}


def cmd_resume_pdf(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    folder = _folder(ctx, args.folder)
    _meta(folder)
    if not (folder / "resume.md").is_file():
        raise UsageError("resume.md가 없어요")
    resume_pdf.build(
        folder / "resume.md",
        folder / "resume.pdf",
        ctx.paths.templates / "resume.css",
        ctx.cfg.font_file(),
    )
    ctx.say("resume.pdf를 만들었어요")
    return 0, {"resume_pdf": ctx.paths.rel(folder / "resume.pdf")}


def cmd_apply(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    folder = _folder(ctx, args.folder)
    meta = _meta(folder)
    limit = ctx.cfg.render.max_attempts
    if meta.render.attempts >= limit:
        raise UsageError(f"렌더링 점검은 최대 {limit}회예요. 남은 문제는 note-issue로 기록하세요")
    base = folder / "base"
    plan = load_plan(folder / "tailor.json", _base_dump(folder)["slide_count"])
    data = pptx_apply.apply(base / "portfolio.pptx", plan)
    design_guard.check(base / "portfolio.pptx", data)
    (folder / "portfolio.pptx").write_bytes(data)
    pdf = ctx.render().to_pdf(folder / "portfolio.pptx", folder)
    changed = pptx_apply.edited_slides(plan)
    previews = render_previews(pdf, changed, folder / "preview", ctx.cfg.render.preview_dpi)
    tol = ctx.cfg.render.overflow_tolerance_pt
    base_issues = layout_check.find_issues(
        base / "portfolio.pptx", base / "render" / "portfolio.pdf", tol
    )
    found = layout_check.find_issues(folder / "portfolio.pptx", pdf, tol)
    new = layout_check.new_issues(found, base_issues, plan.portfolio.slide_order)
    kept_visual = [
        i for i in meta.render.remaining_issues if i.kind == "visual" and i.slide not in changed
    ]
    meta.render.attempts += 1
    meta.render.remaining_issues = new + kept_visual
    folders.write_meta(folder, meta)
    changes.write(folder, meta, plan, None, limit)
    issues = meta.render.remaining_issues
    ctx.say(f"포트폴리오 적용 {meta.render.attempts}/{limit}회째")
    ctx.say(*(f"- {changes.issue_text(i)}" for i in issues) or ["렌더링 문제 없음"])
    if previews:
        ctx.say("미리보기: " + ", ".join(ctx.paths.rel(p) for p in previews))
    return (3 if issues else 0), {
        "attempt": meta.render.attempts,
        "issues": [i.model_dump() for i in issues],
        "previews": [str(p.relative_to(folder)) for p in previews],
    }


def cmd_note_issue(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    folder = _folder(ctx, args.folder)
    meta = _meta(folder)
    meta.render.remaining_issues.append(
        RenderIssue(slide=args.slide, kind="visual", detail=args.detail)
    )
    folders.write_meta(folder, meta)
    changes.write(folder, meta, _plan_or_none(folder), None, ctx.cfg.render.max_attempts)
    ctx.say(f"슬라이드 {args.slide} 문제를 기록했어요")
    return 0, {"issues": len(meta.render.remaining_issues)}


def _verify(ctx: Ctx, folder: Path, meta: Meta):
    result, plan = verify.verify(folder, meta)
    if result.fit_score is not None and meta.status == "in_progress":
        meta.fit_score = result.fit_score
        folders.write_meta(folder, meta)
    warnings = {"unresolved": result.unresolved, "acknowledged": result.acknowledged}
    if (folder / "base" / "portfolio.json").is_file():
        changes.write(folder, meta, plan, warnings, ctx.cfg.render.max_attempts)
        if "changes.md" in result.missing:
            result.missing.remove("changes.md")
            result.ok = not result.missing and not result.problems
    return result


def _say_verify(ctx: Ctx, result) -> None:
    ctx.say(*(f"❌ 없음: {m}" for m in result.missing), *(f"❌ {p}" for p in result.problems))
    ctx.say(*(f"⚠️ 근거 없음: {w['file']} {w['token']} ({w['kind']})" for w in result.unresolved))
    if result.ok and not result.unresolved:
        ctx.say("✅ 검사 통과")


def cmd_verify(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    folder = _folder(ctx, args.folder)
    meta = _meta(folder, editable=False)
    result = _verify(ctx, folder, meta)
    _say_verify(ctx, result)
    return 0, result.json()


def cmd_complete(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    folder = _folder(ctx, args.folder)
    meta = folders.read_meta(folder)
    rel = ctx.paths.rel(folder)
    if meta.status == "done":
        ctx.say(f"이미 완료된 폴더예요: {rel}")
        return 0, _complete_result(meta)
    meta = _meta(folder)
    result = _verify(ctx, folder, meta)
    if not result.ok:
        _say_verify(ctx, result)
        raise UsageError("산출물이 빠졌거나 형식이 맞지 않아 완료할 수 없어요")
    if result.unresolved:
        _say_verify(ctx, result)
        raise UnresolvedWarnings(
            f"근거가 확인되지 않은 항목 {len(result.unresolved)}개가 남아 있어요"
        )
    job_md = (folder / "job.md").read_text(encoding="utf-8")
    text = report.completion(meta, job_md, rel, result.summary, ctx.today)
    if meta.posting.origin == "slack":
        _report_to_slack(ctx, folder, meta, text)
    meta.move("done")
    meta.completed_at = ctx.now.astimezone(KST)
    folders.write_meta(folder, meta)
    changes.write(
        folder,
        meta,
        _plan_or_none(folder),
        {"unresolved": result.unresolved, "acknowledged": result.acknowledged},
        ctx.cfg.render.max_attempts,
    )
    ctx.say(text)
    return 0, _complete_result(meta)


def _complete_result(meta: Meta) -> dict[str, Any]:
    return {
        "status": meta.status,
        "reply_ts": meta.slack.reply_ts,
        "fit_score": meta.fit_score,
        "remaining_issues": len(meta.render.remaining_issues),
    }


def _report_to_slack(ctx: Ctx, folder: Path, meta: Meta, text: str) -> None:
    """Reply → two PDFs → ✅, each recorded in ``meta.slack`` so a rerun resumes (FR-020)."""
    token, channel = slack_token(ctx.environ), slack_channel(ctx.cfg, ctx.environ)
    thread = meta.posting.message_ts
    try:
        if not meta.slack.reply_ts:
            _ch, meta.slack.reply_ts = post_message(
                token, channel, {"text": text}, thread_ts=thread, **ctx.slack_kw
            )
            folders.write_meta(folder, meta)
        if not meta.slack.files_uploaded:
            resume_name, portfolio_name = report.file_names(meta.posting.company, meta.posting.role)
            upload_files(
                token,
                channel,
                [
                    (resume_name, (folder / "resume.pdf").read_bytes()),
                    (portfolio_name, (folder / "portfolio.pdf").read_bytes()),
                ],
                thread_ts=thread,
                **ctx.slack_kw,
            )
            meta.slack.files_uploaded = True
            folders.write_meta(folder, meta)
        if not meta.slack.reacted:
            add_reaction(token, channel, thread, inbox.DONE, **ctx.slack_kw)
            meta.slack.reacted = True
            folders.write_meta(folder, meta)
    except SlackApiError as exc:
        raise SlackError(f"Slack 완료 보고 실패: {exc} (다시 실행하면 이어서 해요)") from None


def cmd_skip(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    try:
        posting, _text = inbox.load_posting(ctx.paths, args.id)
    except FileNotFoundError:
        raise UsageError(f"수집한 공고가 없어요: {args.id}") from None
    if args.reason == "expired" and args.mark_done and args.deadline is None:
        raise UsageError("--mark-done에는 --deadline YYYY-MM-DD가 필요해요")
    if posting.origin == "direct":
        return 0, {"id": posting.id, "slack": False}
    if args.reason == "duplicate":
        done = dedup.find_done(ctx.paths.applications, posting.url_key)
        if done is None:
            raise UsageError("이미 처리한 폴더를 찾지 못했어요")
        text = report.duplicate(ctx.paths.rel(done), folders.read_meta(done).fit_score)
    elif args.mark_done:
        text = report.expired(args.deadline)
    else:
        ctx.say("이번 실행에서만 건너뛰어요")
        return 0, {"id": posting.id, "slack": False}
    token, channel = slack_token(ctx.environ), slack_channel(ctx.cfg, ctx.environ)
    try:
        post_message(token, channel, {"text": text}, thread_ts=posting.message_ts, **ctx.slack_kw)
        add_reaction(token, channel, posting.message_ts, inbox.DONE, **ctx.slack_kw)
    except SlackApiError as exc:
        raise SlackError(f"Slack 오류: {exc}") from None
    ctx.say(text)
    return 0, {"id": posting.id, "slack": True}


def cmd_fail(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    folder = _folder(ctx, args.folder)
    meta = _meta(folder)
    _mark_failed(folder, meta, args.step, args.reason)
    ctx.say(f"실패로 기록했어요: {args.step} — {args.reason}")
    return 0, {"status": "failed"}


def _mark_failed(folder: Path, meta: Meta, step: str, reason: str) -> None:
    if meta.status != "failed":
        meta.move("failed")
    meta.error = MetaError(step=step, reason=reason)
    folders.write_meta(folder, meta)


def cmd_status(ctx: Ctx, args) -> tuple[int, dict[str, Any]]:
    rows = sorted(
        folders.iter_folders(ctx.paths.applications), key=lambda fm: fm[0].name, reverse=True
    )
    if not args.all:
        rows = rows[:20]
    items = []
    for folder, meta in rows:
        fit = f"{meta.fit_score}/100" if meta.fit_score is not None else "-"
        ctx.say(f"{folder.name}  {meta.status}  적합도 {fit}")
        items.append(
            {"folder": ctx.paths.rel(folder), "status": meta.status, "fit_score": meta.fit_score}
        )
    if not items:
        ctx.say("지원 폴더가 없어요")
    return 0, {"folders": items}


COMMANDS = {
    "doctor": cmd_doctor,
    "inbox": cmd_inbox,
    "fetch": cmd_fetch,
    "init": cmd_init,
    "resume-pdf": cmd_resume_pdf,
    "apply": cmd_apply,
    "note-issue": cmd_note_issue,
    "verify": cmd_verify,
    "complete": cmd_complete,
    "skip": cmd_skip,
    "fail": cmd_fail,
    "status": cmd_status,
}


# --- entry ------------------------------------------------------------------------------


def _log_to_file(paths: Paths) -> None:
    root = logging.getLogger()
    target = str((paths.logs / "job.log").resolve())
    for h in [h for h in root.handlers if getattr(h, "_job_log", False)]:
        if h.baseFilename == target:
            return
        root.removeHandler(h)
        h.close()
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(paths.logs / "job.log", encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretMaskingFilter())
    handler.setLevel(logging.INFO)
    handler._job_log = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def emit(out: IO[str], result: dict[str, Any]) -> None:
    out.write("JOB_RESULT " + json.dumps(result, ensure_ascii=False, default=str) + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = AGENT_ROOT,
    environ: Mapping[str, str] | None = None,
    renderer: Renderer | None = None,
    http_factory: Callable[[], httpx.Client] = httpx.Client,
    now: datetime | None = None,
    out: IO[str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    base_delay: float = 1.0,
) -> int:
    out = out or sys.stdout
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    paths = Paths(root)
    _log_to_file(paths)
    with http_factory() as http:
        ctx = Ctx(
            paths=paths,
            environ=os.environ if environ is None else environ,
            http=http,
            now=now or datetime.now(UTC),
            out=out,
            renderer=renderer,
            run=run,
            which=which,
            base_delay=base_delay,
        )
        try:
            with sources.guard(paths):
                code, result = COMMANDS[args.command](ctx, args)
        except SourceChangedError as exc:
            if ctx.folder is not None and (ctx.folder / "meta.json").is_file():
                meta = folders.read_meta(ctx.folder)
                if meta.status != "done":
                    _mark_failed(ctx.folder, meta, args.command, "원본이 처리 중에 바뀜")
            code, result = exc.exit_code, {"error": str(exc)}
            ctx.say(f"❌ {exc}")
        except JobError as exc:
            log.warning(
                "command_failed",
                extra={"fields": {"command": args.command, "error": type(exc).__name__}},
            )
            code, result = exc.exit_code, {"error": str(exc)}
            if isinstance(exc, DuplicatePosting):
                result["duplicate_of"] = exc.folder
            ctx.say(f"❌ {exc}")
        except Exception as exc:  # noqa: BLE001 - exit 1 with a message, never a traceback
            log.exception("unexpected_error")
            code, result = 1, {"error": f"{type(exc).__name__}: {exc}"}
            ctx.say(f"❌ 예상하지 못한 오류: {type(exc).__name__}: {exc}")
    emit(out, {**result, "exit": code} if code else result)
    return code
