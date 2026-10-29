from ja_support.meta import make_folder
from job_apply import dedup


def test_url_key_normalization():
    a = dedup.url_key(
        "HTTPS://Jobs.Example.com/p/1/?utm_source=x&b=2&a=1&ref=y&fbclid=z&gclid=q#top"
    )
    assert a == "https://jobs.example.com/p/1?a=1&b=2"
    assert dedup.url_key("https://jobs.example.com/p/1") == "https://jobs.example.com/p/1"


def test_text_key():
    key = dedup.text_key("  본문  ")
    assert key.startswith("text:") and len(key) == 21 and key == dedup.text_key("본문")


def test_only_done_folders_are_duplicates(tmp_path):
    make_folder(tmp_path, "a", status="failed", url_key="k")
    assert dedup.find_done(tmp_path, "k") is None
    done = make_folder(tmp_path, "b", status="done", url_key="k", posting_id="t-2")
    assert dedup.find_done(tmp_path, "k") == done
