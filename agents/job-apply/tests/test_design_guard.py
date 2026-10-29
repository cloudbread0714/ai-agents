import io
import re
import zipfile

import pytest

from ja_support import session
from ja_support.samples import make_portfolio_pptx
from job_apply.design_guard import check
from job_apply.errors import DesignViolation
from job_apply.models import parse_plan
from job_apply.pptx_apply import apply

EDITS = [
    {
        "slide": 2,
        "shape_id": 3,
        "paragraph": 1,
        "text": "응답 시간 개선",
        "source": "portfolio.json:s2/sh3/p1",
        "reason": "문구를 짧게 정리",
    },
    {
        "slide": 2,
        "shape_id": 3,
        "paragraph": 0,
        "op": {"kind": "insert_after", "text": "추가 문단"},
        "source": "portfolio.json:s2/sh3/p0",
        "reason": "근거 문단 추가",
    },
]


@pytest.fixture
def deck(tmp_path):
    return make_portfolio_pptx(tmp_path / "deck.pptx")


def _result(deck, order=None):
    return apply(deck, parse_plan(session.plan(edits=EDITS, order=order), 5))


def _mutate(blob: bytes, name: str, fn) -> bytes:
    src, out = zipfile.ZipFile(io.BytesIO(blob)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            dst.writestr(item, fn(data) if item.filename == name else data)
    return out.getvalue()


def _sub(pattern, repl, count=1):
    return lambda data: re.sub(pattern.encode(), repl.encode(), data, count=count)


def test_text_and_reorder_pass(deck):
    check(deck, _result(deck, order=[2, 1, 3, 4, 5]))


def _repack(blob: bytes, fn) -> bytes:
    """Rewrite the deck the way some editors save it, keeping every part's meaning."""
    src, out = zipfile.ZipFile(io.BytesIO(blob)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        dirs = sorted({n.rsplit("/", 1)[0] + "/" for n in src.namelist() if "/" in n})
        for d in dirs:
            dst.writestr(d, b"")
        for item in src.infolist():
            dst.writestr(item.filename, fn(item.filename, src.read(item.filename)))
    return out.getvalue()


def _editor_style(name: str, data: bytes) -> bytes:
    if name.endswith(".rels"):  # same relationships, reversed order
        head, *rels = re.split(rb"(?=<Relationship )", data.replace(b"</Relationships>", b""))
        return head + b"".join(reversed(rels)) + b"</Relationships>"
    if name == "[Content_Types].xml":  # an extension no part uses
        return data.replace(
            b"<Default ", b'<Default Extension="gif" ContentType="image/gif"/><Default ', 1
        )
    return data


def test_editor_packaging_differences_pass(tmp_path, deck):
    base = tmp_path / "editor.pptx"
    base.write_bytes(_repack(deck.read_bytes(), _editor_style))
    check(base, apply(base, parse_plan(session.plan(edits=EDITS), 5)))


def test_content_type_change_is_rejected(deck):
    result = _result(deck)
    mutated = _mutate(
        result,
        "[Content_Types].xml",
        _sub(r'Extension="png" ContentType="[^"]+"', 'Extension="png" ContentType="image/x-other"'),
    )
    assert mutated != result
    with pytest.raises(DesignViolation):
        check(deck, mutated)


@pytest.mark.parametrize(
    ("part", "mutation"),
    [
        ("ppt/slides/slide2.xml", _sub(r'<a:off x="(\d+)"', '<a:off x="1"')),  # position
        ("ppt/slides/slide2.xml", _sub(r'<a:ext cx="(\d+)"', '<a:ext cx="1"')),  # size
        (
            "ppt/slides/slide2.xml",
            _sub(r"<p:spPr>", '<p:spPr><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'),
        ),
        ("ppt/slides/slide3.xml", _sub(r'r:embed="rId\d+"', 'r:embed="rId1"')),  # picture
        ("ppt/slides/_rels/slide2.xml.rels", _sub(r"slideLayout7", "slideLayout1")),  # layout
        ("ppt/theme/theme1.xml", _sub(r'<a:srgbClr val="[0-9A-F]{6}"', '<a:srgbClr val="123456"')),
        ("ppt/slideMasters/slideMaster1.xml", _sub(r"<p:cSld>", '<p:cSld name="x">')),
        (
            "ppt/slides/slide2.xml",
            _sub(r"<a:rPr ", '<a:rPr i="1" '),
        ),  # new run format
    ],
)
def test_design_changes_are_rejected(deck, part, mutation):
    result = _result(deck)
    mutated = _mutate(result, part, mutation)
    assert mutated != result
    with pytest.raises(DesignViolation):
        check(deck, mutated)
    assert DesignViolation.exit_code == 4


def test_media_bytes_must_match(deck):
    result = _result(deck)
    media = next(
        n for n in zipfile.ZipFile(io.BytesIO(result)).namelist() if n.startswith("ppt/media/")
    )
    with pytest.raises(DesignViolation):
        check(deck, _mutate(result, media, lambda d: d + b"\0"))


def test_apply_writes_nothing_on_violation(job, httpx_mock, monkeypatch):
    from ja_support.flow import start
    from job_apply import cli

    _id, folder = start(job, httpx_mock)
    session.write(folder)

    def bad(base, data):
        raise DesignViolation("디자인 보존 위반: 테스트")

    monkeypatch.setattr(cli.design_guard, "check", bad)
    code, res, out = job("apply", str(folder))
    assert code == 4 and "디자인 보존 위반" in out
    assert not (folder / "portfolio.pptx").exists()
