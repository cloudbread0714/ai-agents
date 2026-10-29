from ja_support.samples import make_portfolio_pptx
from job_apply.pptx_dump import dump_file


def test_dump_structure(tmp_path):
    data = dump_file(make_portfolio_pptx(tmp_path / "deck.pptx"), tmp_path / "portfolio.json")
    assert (tmp_path / "portfolio.json").is_file()
    assert data["slide_count"] == 5
    s1, s2, _s3, _s4, s5 = data["slides"]
    assert s1["title"] == "홍길동 포트폴리오" and s2["title"] is None
    intro = s2["shapes"][0]
    assert (intro["shape_id"], intro["name"], intro["box_pt"]) == (
        2,
        "Intro",
        [40.0, 40.0, 680.0, 100.0],
    )
    assert intro["paragraphs"] == [
        {
            "paragraph": 0,
            "text": "핵심 역량: Python 백엔드",
            "runs": ["핵심 역량: ", "Python 백엔드"],
            "level": 0,
        }
    ]
    bullets = s2["shapes"][1]["paragraphs"]
    assert [(p["text"], p["level"]) for p in bullets] == [
        ("API 서버 설계", 0),
        ("응답 시간 30% 개선", 1),
        ("PostgreSQL 운영", 0),
    ]
    table, grouped = s5["shapes"]
    assert table["table"] is True and "paragraphs" not in table
    assert grouped["name"] == "Grouped" and grouped["paragraphs"][0]["text"] == "그룹 안 텍스트"
    assert grouped["box_pt"] == [40.0, 200.0, 340.0, 260.0]


def test_picture_shapes_are_not_listed(tmp_path):
    data = dump_file(make_portfolio_pptx(tmp_path / "deck.pptx"))
    assert [s["name"] for s in data["slides"][2]["shapes"]] == ["Caption"]
