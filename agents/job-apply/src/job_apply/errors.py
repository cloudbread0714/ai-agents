"""Errors with the exit codes of contracts/cli.md."""

from __future__ import annotations


class JobError(Exception):
    exit_code = 1


class UsageError(JobError):
    """Bad arguments or a bad file the session wrote (tailor.json, resume.md frontmatter)."""

    exit_code = 2


class PlanError(UsageError):
    """tailor.json breaks the schema or points at something that does not exist."""


class DesignViolation(JobError):
    exit_code = 4


class EnvNotReady(JobError):
    """Original missing, LibreOffice missing, token missing, gitignore not applied."""

    exit_code = 5


class SourceError(EnvNotReady):
    pass


class DuplicatePosting(JobError):
    exit_code = 6

    def __init__(self, folder: str):
        super().__init__(f"이미 처리한 공고예요: {folder}")
        self.folder = folder


class SlackError(JobError):
    exit_code = 7


class SourceChangedError(JobError):
    exit_code = 8

    def __init__(self, names: list[str]):
        super().__init__(f"원본이 처리 중에 바뀜: {', '.join(names)}")
        self.names = names


class RenderError(JobError):
    """LibreOffice ran but did not produce a PDF (timeout, crash)."""


class UnresolvedWarnings(JobError):
    """Provenance warnings left without an acknowledgement (``complete``)."""

    exit_code = 9
