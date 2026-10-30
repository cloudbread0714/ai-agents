"""``job doctor``: is this machine ready for /tailor and /job-run (contracts/cli.md doctor)?"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from job_apply import sources
from job_apply.config import JobConfig, Paths, slack_channel, slack_token
from job_apply.errors import EnvNotReady
from shared.slack import SlackApiError, auth_test, conversations_history

Run = Callable[..., subprocess.CompletedProcess]
_TYPEFACE = re.compile(rb'<a:(?:latin|ea|cs)\b[^>]*\btypeface="([^"]+)"')
_RFONT = re.compile(rb"<w:rFonts\b[^>]*>")
_RFONT_NAME = re.compile(rb'\bw:(?:ascii|hAnsi|eastAsia|cs)="([^"]+)"')


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    slack_ready: bool = False

    def good(self, text: str) -> None:
        self.lines.append(f"✅ {text}")

    def bad(self, key: str, text: str) -> None:
        self.lines.append(f"❌ {text}")
        self.missing.append(key)

    def warn(self, text: str) -> None:
        self.lines.append(f"⚠️ {text}")
        self.warnings.append(text)

    def result(self) -> dict[str, Any]:
        return {
            "ok": not self.missing,
            "slack_ready": self.slack_ready,
            "missing": self.missing,
            "warnings": self.warnings,
        }


def pptx_fonts(pptx) -> set[str]:
    names: set[str] = set()
    with zipfile.ZipFile(pptx) as z:
        for name in z.namelist():
            if name.endswith(".xml") and name.startswith("ppt/"):
                for face in _TYPEFACE.findall(z.read(name)):
                    face = face.decode("utf-8", "replace")
                    if face and not face.startswith("+"):
                        names.add(face)
    return names


def docx_fonts(docx) -> set[str]:
    """Fonts named directly in the document and its styles (theme fonts are skipped)."""
    names: set[str] = set()
    with zipfile.ZipFile(docx) as z:
        for part in ("word/document.xml", "word/styles.xml"):
            if part in z.namelist():
                for tag in _RFONT.findall(z.read(part)):
                    names |= {f.decode("utf-8", "replace") for f in _RFONT_NAME.findall(tag)}
    return names


def installed_fonts(run: Run, which: Callable[[str], str | None]) -> set[str] | None:
    if not which("fc-list"):
        return None
    proc = run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=30)
    families: set[str] = set()
    for line in proc.stdout.splitlines():
        families |= {f.strip() for f in line.split(",") if f.strip()}
    return families


def run_checks(
    paths: Paths,
    cfg: JobConfig,
    environ: Mapping[str, str],
    *,
    run: Run = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    slack_kw: dict[str, Any],
    repo_root,
) -> Report:
    rep = Report()
    try:
        sources.check(paths)
        rep.good("원본 이력서·포트폴리오가 있고 열려요")
        sources_ok = True
    except EnvNotReady as exc:
        rep.bad("sources", str(exc))
        sources_ok = False

    if which("soffice"):
        rep.good("LibreOffice(soffice)가 있어요")
    else:
        rep.bad("soffice", "LibreOffice(soffice)가 없어요: brew install --cask libreoffice")

    if sources_ok:
        installed = installed_fonts(run, which)
        if installed is None:
            rep.warn("fc-list가 없어 이력서·포트폴리오 글꼴 확인을 건너뛰었어요")
        else:
            for label, fonts in (
                ("이력서", docx_fonts(paths.resume)),
                ("포트폴리오", pptx_fonts(paths.portfolio)),
            ):
                subs = cfg.render.font_substitutes
                absent = sorted(
                    f for f in fonts if f not in installed and subs.get(f) not in installed
                )
                if absent:
                    rep.warn(
                        f"{label} 글꼴이 설치돼 있지 않아요(줄 바꿈이 달라질 수 있음): "
                        + ", ".join(absent)
                    )
                else:
                    rep.good(f"{label} 글꼴이 모두 설치돼 있어요")

    private = [paths.rel(p / "x") for p in (paths.private, paths.applications, paths.state)]
    proc = run(
        ["git", "check-ignore", *private], capture_output=True, text=True, cwd=repo_root, timeout=30
    )
    ignored = set(proc.stdout.split())
    not_ignored = [p for p in private if p not in ignored]
    if not_ignored:
        rep.bad(
            "gitignore",
            "git이 무시하지 않는 개인정보 경로: "
            + ", ".join(p.removesuffix("/x") for p in not_ignored),
        )
    else:
        rep.good("private/, applications/, .job-state/는 git에서 무시돼요")

    try:
        token = slack_token(environ)
        channel = slack_channel(cfg, environ)
        auth_test(token, **slack_kw)
        conversations_history(token, channel, limit=1, **slack_kw)
        rep.slack_ready = True
        rep.good("Slack 연결과 #job-apply 읽기 권한 확인")
    except (EnvNotReady, SlackApiError) as exc:
        rep.warn(f"Slack 준비 안 됨(/job-run 불가, /tailor는 가능): {exc}")
    return rep
