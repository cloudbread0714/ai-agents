from troubleshoot_lab.session import ActiveMission, Session


def test_set_get_clear(tmp_path):
    s = Session(tmp_path)
    assert s.get() is None
    s.set("m-one", 1)
    assert s.get() == ActiveMission("m-one", 1)
    s.clear()
    assert s.get() is None
    s.clear()  # clearing twice is fine


def test_corrupt_file_is_empty(tmp_path):
    (tmp_path / "session.json").write_text("{not json")
    assert Session(tmp_path).get() is None
    (tmp_path / "session.json").write_text('{"id": "x"}')
    assert Session(tmp_path).get() is None
