"""Sample API that the lab breaks and the learner fixes.

Every endpoint exercises one dependency (PostgreSQL, Redis, the ext service, the log
disk, memory, CPU). Fault switches are environment variables whose defaults are the
healthy behavior; scenarios turn them on through the compose override (research R19).
"""

from __future__ import annotations

import json
import logging
import os
import random
import socket
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Any, Protocol
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("lab-api")

# Memory deliberately kept alive by LEAK_MB_PER_REQ (#8).
LEAKED: list[bytearray] = []
# Sockets deliberately never closed by LEAK_SOCKETS (#10); referenced so GC cannot close them.
LEAKED_SOCKETS: list[socket.socket] = []


class PoolTimeoutError(Exception):
    """No database connection became free in time."""


class ExtTimeout(Exception):
    """The ext service did not answer within the timeout."""


class Store(Protocol):
    def ping(self) -> None: ...
    def list_items(self, leak: bool = False) -> list[str]: ...
    def add_item(self, name: str) -> None: ...
    def catalog_item(self, item_id: int) -> dict[str, Any]: ...
    def popular(self) -> list[dict[str, Any]]: ...
    def orders(self, customer: int) -> dict[str, Any]: ...


class Cache(Protocol):
    def ping(self) -> None: ...
    def incr(self, key: str) -> int: ...
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, px: int, nx: bool = False) -> bool: ...
    def delete(self, key: str) -> None: ...


class Ext(Protocol):
    def get(self, path: str, timeout: float | None = None, leak: bool = False) -> dict: ...


# --- real dependencies -----------------------------------------------------------------


class PgStore:
    def __init__(self, url: str, pool_size: int):
        from psycopg_pool import ConnectionPool

        # 2 s, shorter than nginx's 3 s proxy timeout, so pool exhaustion is a 503 not a 504.
        self.pool = ConnectionPool(url, min_size=1, max_size=pool_size, timeout=2, open=False)
        self.pool.open(wait=False)

    def _conn(self):
        from psycopg_pool import PoolTimeout

        try:
            return self.pool.getconn()
        except PoolTimeout as exc:
            raise PoolTimeoutError(str(exc)) from None

    def _query(self, sql: str, params: tuple = (), *, leak: bool = False):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if cur.description else []
            conn.commit()
            return rows
        finally:
            if not leak:  # the bug in #12: this path forgets to give the connection back
                self.pool.putconn(conn)

    def ping(self) -> None:
        self._query("SELECT 1")

    def list_items(self, leak: bool = False) -> list[str]:
        return [r[0] for r in self._query("SELECT name FROM items ORDER BY id", leak=leak)]

    def add_item(self, name: str) -> None:
        self._query("INSERT INTO items (name) VALUES (%s)", (name,))

    def catalog_item(self, item_id: int) -> dict[str, Any]:
        rows = self._query("SELECT %s, 'item-' || %s, pg_sleep(0.02)", (item_id, item_id))
        return {"id": rows[0][0], "name": rows[0][1]}

    def popular(self) -> list[dict[str, Any]]:
        rows = self._query("SELECT id, title, pg_sleep(0.3) FROM popular ORDER BY id LIMIT 5")
        return [{"id": r[0], "title": r[1]} for r in rows]

    def orders(self, customer: int) -> dict[str, Any]:
        rows = self._query(
            "SELECT count(*), coalesce(sum(amount), 0) FROM orders WHERE customer_id = %s",
            (customer,),
        )
        return {"customer": customer, "orders": rows[0][0], "total": rows[0][1]}


class RedisCache:
    def __init__(self, url: str):
        import redis

        self.client = redis.Redis.from_url(
            url, socket_connect_timeout=3, socket_timeout=3, decode_responses=True
        )

    def ping(self) -> None:
        self.client.ping()

    def incr(self, key: str) -> int:
        return int(self.client.incr(key))

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str, px: int, nx: bool = False) -> bool:
        return bool(self.client.set(key, value, px=px, nx=nx))

    def delete(self, key: str) -> None:
        self.client.delete(key)


class SocketExt:
    """Minimal HTTP/1.1 client on a raw socket, so #10 can 'forget' to close it."""

    def __init__(self, url: str):
        parsed = urlparse(url)
        self.host = parsed.hostname or "ext"
        self.port = parsed.port or 80

    def get(self, path: str, timeout: float | None = None, leak: bool = False) -> dict:
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        try:
            request = f"GET {path} HTTP/1.1\r\nHost: {self.host}\r\nConnection: close\r\n\r\n"
            sock.sendall(request.encode())
            chunks = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
        except TimeoutError:
            sock.close()
            raise ExtTimeout(path) from None
        if leak:
            LEAKED_SOCKETS.append(sock)  # the server closed its side; ours stays in CLOSE_WAIT
        else:
            sock.close()
        body = b"".join(chunks).split(b"\r\n\r\n", 1)[-1]
        return json.loads(body or b"{}")


# --- app ---------------------------------------------------------------------------------


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


StoreDep = Annotated[Store, Depends(get_store)]
CacheDep = Annotated[Cache, Depends(get_cache)]


class NewItem(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def sum_of_squares(n: int) -> int:
    return (n - 1) * n * (2 * n - 1) // 6


def _flag(env: Mapping[str, str], name: str, default: str = "0") -> bool:
    return env.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, default))
    except ValueError:
        return default


def create_app(
    env: Mapping[str, str] | None = None,
    *,
    store: Store | None = None,
    cache: Cache | None = None,
    ext: Ext | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> FastAPI:
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    rng = rng or random.Random()
    if env.get("APP_ROLE") == "ext":
        return _ext_app(env, sleep, rng)

    if store is None:
        if not env.get("DATABASE_URL"):
            log.error("DATABASE_URL is not set; cannot start")
            raise SystemExit(1)
        store = PgStore(env["DATABASE_URL"], _int(env, "DB_POOL_SIZE", 10))
    if cache is None:
        cache = RedisCache(env.get("REDIS_URL", "redis://redis:6379/0"))
    if ext is None:
        ext = SocketExt(env.get("EXT_URL", "http://ext:8000"))

    app = FastAPI(title="lab-api")
    app.state.store, app.state.cache, app.state.ext = store, cache, ext
    version = env.get("APP_VERSION", "1.0.0")
    log_dir = Path(env.get("LOG_DIR", "/tmp/lab-api-logs"))

    def write_log(message: str) -> None:
        lines = 200 if _flag(env, "LOG_VERBOSE") else 1
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "app.log").open("a", encoding="utf-8") as f:
            for i in range(lines):
                f.write(
                    f"{time.time():.3f} {message} detail={i} {'x' * (900 if lines > 1 else 0)}\n"
                )

    def leak_memory() -> None:
        mb = _int(env, "LEAK_MB_PER_REQ", 0)
        if mb > 0:
            LEAKED.append(bytearray(mb * 1024 * 1024))

    @app.exception_handler(PoolTimeoutError)
    def pool_timeout(_request: Request, _exc: PoolTimeoutError):
        return JSONResponse({"error": "db pool timeout"}, status_code=503)

    @app.exception_handler(OSError)
    def disk_error(_request: Request, exc: OSError):
        log.error("io error: %s", exc)
        return JSONResponse({"error": f"io error: {exc.strerror or exc}"}, status_code=500)

    @app.get("/healthz")
    def healthz(store: StoreDep, cache: CacheDep):
        checks = {}
        for name, dep in (("db", store), ("redis", cache)):
            try:
                dep.ping()
                checks[name] = "ok"
            except Exception as exc:  # noqa: BLE001 - any dependency failure means unhealthy
                checks[name] = type(exc).__name__
        ok = all(v == "ok" for v in checks.values())
        body = {"status": "ok" if ok else "fail", **checks}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/items")
    def list_items(response: Response, store: StoreDep):
        leak_memory()
        write_log("GET /items")
        response.headers["Cache-Control"] = "no-store"
        return {"items": store.list_items(leak=_flag(env, "LEAK_DB_CONN"))}

    @app.post("/items", status_code=201)
    def add_item(item: NewItem, store: StoreDep):
        write_log(f"POST /items name={item.name}")
        store.add_item(item.name)
        return {"added": item.name}

    @app.get("/report")
    def report():
        n = _int(env, "REPORT_N", 3_000_000)
        if env.get("REPORT_ALGO", "fast") == "naive":
            result = 0
            for i in range(n):
                result += i * i
        else:
            result = sum_of_squares(n)
        delay = _int(env, "REPORT_DELAY_MS", 0)
        if delay > 0:
            sleep(delay / 1000)
        return {"n": n, "result": result}

    @app.get("/upstream")
    def upstream(request: Request):
        return {"upstream": request.app.state.ext.get("/ext/ping", 3.0, _flag(env, "LEAK_SOCKETS"))}

    @app.get("/catalog/{item_id}")
    def catalog(item_id: int, response: Response, store: StoreDep, cache: CacheDep):
        key = f"catalog:{item_id}"
        cached = cache.get(key)
        if cached is not None:
            response.headers["X-Cache"] = "HIT"
            return json.loads(cached)
        item = store.catalog_item(item_id)
        cache.set(key, json.dumps(item), px=max(1, _int(env, "CACHE_TTL_MS", 30000)))
        response.headers["X-Cache"] = "MISS"
        return item

    @app.get("/popular")
    def popular(response: Response, store: StoreDep, cache: CacheDep):
        cached = cache.get("popular")
        if cached is not None:
            response.headers["X-Cache"] = "HIT"
            return {"popular": json.loads(cached)}
        response.headers["X-Cache"] = "MISS"
        if _flag(env, "CACHE_LOCK", "1") and not cache.set("popular:lock", "1", px=5000, nx=True):
            for _ in range(40):  # someone else is rebuilding: wait for their result
                sleep(0.05)
                cached = cache.get("popular")
                if cached is not None:
                    return {"popular": json.loads(cached)}
        log.info("popular rebuild")  # one line per DB rebuild; #14 counts these
        data = store.popular()
        ttl = max(1, _int(env, "POPULAR_TTL_MS", 10000))
        if _flag(env, "CACHE_JITTER", "1"):
            ttl += rng.randint(0, ttl // 5)
        cache.set("popular", json.dumps(data), px=ttl)
        cache.delete("popular:lock")
        return {"popular": data}

    @app.get("/orders")
    def orders(customer: int, store: StoreDep):
        return store.orders(customer)

    @app.get("/checkout")
    def checkout(request: Request):
        timeout_ms = _int(env, "EXT_TIMEOUT_MS", 1000)
        try:
            result = request.app.state.ext.get(
                "/ext/work", timeout_ms / 1000 if timeout_ms > 0 else None
            )
        except ExtTimeout:
            return {"status": "queued", "fallback": True}
        return {"status": "done", "fallback": False, "ext": result}

    @app.get("/counter")
    def count(cache: CacheDep):
        return {"count": cache.incr("lab:counter")}

    @app.get("/profile")
    def profile(request: Request, response: Response):
        response.headers["Cache-Control"] = "private, no-store"
        return {"user": request.cookies.get("user", "guest")}

    @app.get("/version")
    def get_version():
        return {"version": version}

    return app


def _ext_app(env: Mapping[str, str], sleep: Callable[[float], None], rng: random.Random) -> FastAPI:
    """APP_ROLE=ext: the 'external dependency' used by /upstream and /checkout."""
    app = FastAPI(title="lab-ext")
    ratio = float(env.get("EXT_SLOW_RATIO", "0") or 0)
    slow_s = _int(env, "EXT_SLOW_MS", 0) / 1000

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/ext/ping")
    def ping():
        return {"pong": True}

    @app.get("/ext/work")
    def work():
        if slow_s > 0 and rng.random() < ratio:
            sleep(slow_s)
        return {"worked": True}

    return app
