from shared.files import write_text_atomic


def test_write_creates_dirs_and_replaces(tmp_path):
    target = tmp_path / "a" / "b.json"
    write_text_atomic(target, "one")
    write_text_atomic(target, "two")
    assert target.read_text() == "two"
    assert [p.name for p in target.parent.iterdir()] == ["b.json"]  # no temp files left


def test_failed_write_leaves_old_content(tmp_path, monkeypatch):
    target = tmp_path / "x.json"
    write_text_atomic(target, "old")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("shared.files.os.replace", boom)
    try:
        write_text_atomic(target, "new")
    except OSError:
        pass
    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]
