import subprocess

from troubleshoot_lab.sync import PROGRESS_REL, REPORTS_REL, sync


class FakeGit:
    def __init__(self, *, branch="main", dirty=True, ahead="1", push_failures=0):
        self.branch, self.dirty, self.ahead = branch, dirty, ahead
        self.push_failures = push_failures
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(args)
        out, code = "", 0
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            out = self.branch
        elif args[0] == "status":
            out = f" M {PROGRESS_REL}" if self.dirty else ""
        elif args[0] == "rev-list":
            out = self.ahead
        elif args[0] == "push" and self.push_failures:
            self.push_failures -= 1
            code = 1
        return subprocess.CompletedProcess(["git", *args], code, out, "err" if code else "")


def test_refuses_outside_main(tmp_path):
    git = FakeGit(branch="002-lab")
    result = sync(tmp_path, git=git)
    assert result.exit_code == 4 and "002-lab" in result.text
    assert not any(c[0] == "commit" for c in git.calls)


def test_nothing_to_do(tmp_path):
    result = sync(tmp_path, git=FakeGit(dirty=False, ahead="0"))
    assert (result.exit_code, result.outcome) == (0, "unchanged")


def test_commits_only_progress_and_reports_and_pushes(tmp_path):
    git = FakeGit()
    result = sync(tmp_path, git=git, base_delay=0)
    assert (result.exit_code, result.outcome) == (0, "pushed")
    status = next(c for c in git.calls if c[0] == "status")
    assert status[-2:] == [PROGRESS_REL, REPORTS_REL]
    assert ["add", "--", PROGRESS_REL, REPORTS_REL] in git.calls  # new reports are untracked
    commit = next(c for c in git.calls if c[0] == "commit")
    assert commit[-3:] == ["--", PROGRESS_REL, REPORTS_REL]
    assert "[skip ci]" in commit[2]
    assert ["pull", "--rebase", "--autostash", "origin", "main"] in git.calls
    assert ["push", "origin", "HEAD:main"] in git.calls


def test_pushes_an_earlier_unpushed_commit(tmp_path):
    git = FakeGit(dirty=False, ahead="1")
    assert sync(tmp_path, git=git, base_delay=0).outcome == "pushed"
    assert not any(c[0] == "commit" for c in git.calls)


def test_retries_push_then_gives_up_keeping_the_commit(tmp_path):
    git = FakeGit(push_failures=2)
    assert sync(tmp_path, git=git, base_delay=0).outcome == "pushed"
    assert sum(c[0] == "push" for c in git.calls) == 3

    git = FakeGit(push_failures=5)
    result = sync(tmp_path, git=git, base_delay=0)
    assert (result.exit_code, result.outcome) == (1, "failed")
    assert sum(c[0] == "push" for c in git.calls) == 3
    assert "로컬에 남아" in result.text
