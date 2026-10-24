import logging
import random

import pytest
from app.main import ExtTimeout, PoolTimeoutError, create_app, sum_of_squares
from fastapi.testclient import TestClient


class FakeStore:
    def __init__(self, items=None, broken=False, pool_size=10):
        self.items = list(items or [])
        self.broken = broken
        self.pool_size = pool_size
        self.leaked = 0
        self.catalog_reads = 0
        self.popular_reads = 0

    def ping(self):
        if self.broken:
            raise ConnectionError("db down")

    def _take(self, leak):
        if self.leaked >= self.pool_size:
            raise PoolTimeoutError("pool exhausted")
        if leak:
            self.leaked += 1

    def list_items(self, leak=False):
        self._take(leak)
        return list(self.items)

    def add_item(self, name):
        self.items.append(name)

    def catalog_item(self, item_id):
        self.catalog_reads += 1
        return {"id": item_id, "name": f"item-{item_id}"}

    def popular(self):
        self.popular_reads += 1
        return [{"id": 1, "title": "hot"}]

    def orders(self, customer):
        return {"customer": customer, "orders": 3, "total": 300}


class FakeCache:
    def __init__(self, broken=False):
        self.data = {}
        self.broken = broken
        self.ttls = []

    def ping(self):
        if self.broken:
            raise TimeoutError("redis down")

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, px, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        self.ttls.append((key, px))
        return True

    def delete(self, key):
        self.data.pop(key, None)

    def expire_all(self):
        self.data = {k: v for k, v in self.data.items() if k.endswith(":lock")}


class FakeExt:
    def __init__(self, timeout=False):
        self.calls = []
        self.timeout = timeout

    def get(self, path, timeout=None, leak=False):
        self.calls.append((path, timeout, leak))
        if self.timeout and timeout is not None:
            raise ExtTimeout(path)
        return {"ok": True, "path": path}


def client(env=None, store=None, cache=None, ext=None, sleep=None, rng=None, tmp_path=None):
    base = {"APP_VERSION": "1.2.3"}
    if tmp_path is not None:
        base["LOG_DIR"] = str(tmp_path)
    app = create_app(
        {**base, **(env or {})},
        store=store or FakeStore(),
        cache=cache or FakeCache(),
        ext=ext or FakeExt(),
        sleep=sleep or (lambda s: None),
        rng=rng or random.Random(0),
    )
    return TestClient(app)


# --- existing behaviour --------------------------------------------------------------


def test_healthz_ok_when_both_dependencies_answer():
    resp = client().get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok", "redis": "ok"}


@pytest.mark.parametrize(
    "store,cache,failed",
    [(FakeStore(broken=True), FakeCache(), "db"), (FakeStore(), FakeCache(broken=True), "redis")],
)
def test_healthz_503_when_a_dependency_fails(store, cache, failed):
    resp = client(store=store, cache=cache).get("/healthz")
    assert resp.status_code == 503
    assert resp.json()[failed] != "ok"


def test_items_list_and_add(tmp_path):
    store = FakeStore(["a"])
    c = client(store=store, tmp_path=tmp_path)
    assert c.post("/items", json={"name": "b"}).status_code == 201
    resp = c.get("/items")
    assert resp.json() == {"items": ["a", "b"]}
    assert resp.headers["cache-control"] == "no-store"


def test_items_rejects_empty_name():
    assert client().post("/items", json={"name": ""}).status_code == 422


def test_counter_increments():
    c = client()
    assert c.get("/counter").json() == {"count": 1}
    assert c.get("/counter").json() == {"count": 2}


def test_profile_reads_cookie_and_is_private():
    c = client()
    c.cookies.set("user", "alice")
    resp = c.get("/profile")
    assert resp.json() == {"user": "alice"}
    assert "private" in resp.headers["cache-control"]


def test_version_from_env():
    assert client().get("/version").json() == {"version": "1.2.3"}


def test_missing_database_url_exits(caplog):
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
        create_app({"REDIS_URL": "redis://x"}, cache=FakeCache(), ext=FakeExt())
    assert exc.value.code == 1
    assert "DATABASE_URL" in caplog.text


def test_empty_database_url_counts_as_missing():
    with pytest.raises(SystemExit):
        create_app({"DATABASE_URL": ""}, cache=FakeCache(), ext=FakeExt())


# --- fault switches (research R19) ---------------------------------------------------


def test_report_algorithms_agree_and_delay():
    slept = []
    fast = client({"REPORT_N": "1000"}).get("/report").json()
    naive = client({"REPORT_N": "1000", "REPORT_ALGO": "naive"}).get("/report").json()
    assert (
        fast["result"] == naive["result"] == sum_of_squares(1000) == sum(i * i for i in range(1000))
    )
    client({"REPORT_DELAY_MS": "250"}, sleep=slept.append).get("/report")
    assert slept == [0.25]


def test_leaky_db_connections_exhaust_the_pool():
    store = FakeStore(pool_size=3)
    c = client({"LEAK_DB_CONN": "1"}, store=store)
    for _ in range(3):
        assert c.get("/items").status_code == 200
    resp = c.get("/items")
    assert resp.status_code == 503
    assert resp.json() == {"error": "db pool timeout"}


def test_verbose_logging_writes_many_lines(tmp_path):
    client({"LOG_VERBOSE": "1"}, tmp_path=tmp_path).get("/items")
    lines = (tmp_path / "app.log").read_text().splitlines()
    assert len(lines) >= 100
    client(tmp_path=tmp_path).get("/items")
    assert len((tmp_path / "app.log").read_text().splitlines()) == len(lines) + 1


def test_log_write_failure_is_500(tmp_path):
    blocked = tmp_path / "app.log"
    blocked.mkdir()  # writing to a directory fails like a full disk would
    assert client(tmp_path=tmp_path).post("/items", json={"name": "x"}).status_code == 500


def test_memory_leak_grows_per_request():
    from app import main

    main.LEAKED.clear()
    c = client({"LEAK_MB_PER_REQ": "1"})
    c.get("/items")
    c.get("/items")
    assert sum(len(b) for b in main.LEAKED) == 2 * 1024 * 1024
    main.LEAKED.clear()


def test_upstream_closes_or_leaks_socket():
    ext = FakeExt()
    client(ext=ext).get("/upstream")
    client({"LEAK_SOCKETS": "1"}, ext=ext).get("/upstream")
    assert [call[2] for call in ext.calls] == [False, True]


def test_catalog_cache_aside_hit_and_ttl():
    store, cache = FakeStore(), FakeCache()
    c = client({"CACHE_TTL_MS": "30000"}, store=store, cache=cache)
    assert c.get("/catalog/7").headers["x-cache"] == "MISS"
    assert c.get("/catalog/7").headers["x-cache"] == "HIT"
    assert store.catalog_reads == 1
    assert ("catalog:7", 30000) in cache.ttls


def test_popular_lock_allows_one_rebuild():
    store, cache = FakeStore(), FakeCache()
    cache.data["popular:lock"] = "someone"  # another worker is rebuilding
    cache_value_after_wait = {"n": 0}

    def sleep(_s):
        cache_value_after_wait["n"] += 1
        cache.data["popular"] = '[{"id": 1, "title": "hot"}]'

    c = client({"CACHE_LOCK": "1"}, store=store, cache=cache, sleep=sleep)
    assert c.get("/popular").status_code == 200
    assert store.popular_reads == 0  # waited for the other rebuild instead of hitting the DB


def test_popular_without_lock_hits_db_every_miss_and_jitter_varies_ttl():
    store, cache = FakeStore(), FakeCache()
    c = client(
        {"CACHE_LOCK": "0", "CACHE_JITTER": "0", "POPULAR_TTL_MS": "2000"}, store=store, cache=cache
    )
    c.get("/popular")
    cache.expire_all()
    c.get("/popular")
    assert store.popular_reads == 2
    assert {px for key, px in cache.ttls if key == "popular"} == {2000}

    cache2 = FakeCache()
    c2 = client({"CACHE_JITTER": "1", "POPULAR_TTL_MS": "10000"}, cache=cache2)
    for _ in range(5):
        c2.get("/popular")
        cache2.expire_all()
    ttls = {px for key, px in cache2.ttls if key == "popular"}
    assert len(ttls) > 1 and all(10000 <= px <= 12000 for px in ttls)


def test_orders_by_customer():
    assert client().get("/orders", params={"customer": 42}).json()["customer"] == 42


def test_checkout_timeout_falls_back_and_zero_waits():
    ext = FakeExt(timeout=True)
    resp = client({"EXT_TIMEOUT_MS": "1000"}, ext=ext).get("/checkout")
    assert resp.status_code == 200 and resp.json()["fallback"] is True
    assert ext.calls[-1][1] == 1.0
    resp = client({"EXT_TIMEOUT_MS": "0"}, ext=ext).get("/checkout")
    assert resp.json()["fallback"] is False
    assert ext.calls[-1][1] is None


def test_ext_role_delays_a_fraction_of_requests():
    slept = []
    app = create_app(
        {"APP_ROLE": "ext", "EXT_SLOW_RATIO": "0.5", "EXT_SLOW_MS": "5000"},
        sleep=slept.append,
        rng=random.Random(1),
    )
    c = TestClient(app)
    for _ in range(20):
        assert c.get("/ext/work").status_code == 200
    assert 3 <= len(slept) <= 17 and set(slept) == {5.0}
    assert c.get("/healthz").status_code == 200
