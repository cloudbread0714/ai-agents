from datetime import date

from job_apply import folders


def test_clean_names():
    assert folders.clean("예시 회사/주식회사") == "예시-회사주식회사"
    assert folders.clean('a:b*c?"d<e>f|g\x01') == "abcdefg"
    assert folders.clean("ㄱ" * 50) == "ㄱ" * 40
    assert folders.clean("é") == "é"  # NFC
    assert folders.clean("   ") == "미상"
    assert folders.base_name(date(2026, 10, 27), "가상 테크", "백엔드 개발자") == (
        "2026-10-27_가상-테크_백엔드-개발자"
    )


def test_collisions_get_suffixes(tmp_path):
    day = date(2026, 10, 27)
    names = [folders.new_folder(tmp_path, day, "가상테크", "백엔드").name for _ in range(3)]
    assert names == [
        "2026-10-27_가상테크_백엔드",
        "2026-10-27_가상테크_백엔드_2",
        "2026-10-27_가상테크_백엔드_3",
    ]


def test_reuse_only_failed_or_in_progress(tmp_path):
    from ja_support.meta import make_folder

    make_folder(tmp_path, "a", status="done", posting_id="t-1")
    assert folders.find_resumable(tmp_path, "t-1", "k") is None
    failed = make_folder(tmp_path, "b", status="failed", posting_id="t-2", url_key="k2")
    assert folders.find_resumable(tmp_path, "t-x", "k2") == failed
    going = make_folder(tmp_path, "c", status="in_progress", posting_id="t-3", url_key="k3")
    assert folders.find_resumable(tmp_path, "t-3", "other") == going


def test_meta_writes_are_atomic(tmp_path):
    from ja_support.meta import make_meta

    folders.write_meta(tmp_path, make_meta())
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]
    assert folders.read_meta(tmp_path).status == "in_progress"
