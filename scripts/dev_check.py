"""Local startup preflight. Never print URLs/passwords or replace a user's .env."""

import argparse
import asyncio
import json
import sys

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from vision_worker.config import WorkerSettings

LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def local_config(api: Settings, worker: WorkerSettings) -> dict[str, int]:
    if (
        any(host["host"] not in LOOPBACK for host in api.database_url.hosts())
        or api.redis_url.host not in LOOPBACK
    ):
        raise ValueError("Local launcher requires local PG/Redis; existing .env was not changed.")
    if api.api_host != "127.0.0.1" or worker.worker_http_host != "127.0.0.1":
        raise ValueError("Local launcher requires API_HOST/WORKER_HTTP_HOST=127.0.0.1.")
    if str(api.redis_url) != str(worker.redis_url):
        raise ValueError("API and worker must use the same Redis URL.")
    if worker.api_base_url.host not in LOOPBACK or worker.api_base_url.port != api.api_port:
        raise ValueError("API_BASE_URL must point to the local API_PORT.")
    if not api.worker_api_token or not api.worker_api_token.get_secret_value():
        raise ValueError("Set WORKER_API_TOKEN in .env (do not send it in chat).")
    if api.worker_api_token != worker.worker_api_token:
        raise ValueError("API and worker WORKER_API_TOKEN values must match.")
    return {"api_port": api.api_port, "worker_port": worker.worker_http_port}


async def check(api: Settings, seed_if_empty: bool) -> bool:
    redis = Redis.from_url(str(api.redis_url), socket_connect_timeout=3, socket_timeout=3)
    engine = create_async_engine(str(api.database_url), connect_args={"timeout": 3})
    try:
        for name, action in [("Redis", redis.ping), ("PostgreSQL", None)]:
            try:
                async with asyncio.timeout(5):
                    if action:
                        await action()
                    else:
                        async with engine.connect() as conn:
                            await conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001 -- report sanitized diagnostic, never DSNs
                print(
                    f"{name} unavailable ({type(exc).__name__}). Check Docker and .env; "
                    "default local ports: Redis6379, PG15432. "
                    "Use 127.0.0.1 for native Windows processes.",
                    file=sys.stderr,
                )
                return False
        if seed_if_empty:
            async with engine.connect() as conn:
                total = (await conn.execute(text("SELECT count(*) FROM cameras"))).scalar_one()
            if total == 0 and api.max_cameras >= 2:
                from app.seed import seed

                await seed()
                print("Created two DEMO cameras in an empty database.")
            else:
                print("Keeping existing cameras/zones unchanged; no automatic seed.")
        print("Redis PING + PostgreSQL SELECT 1: PASS")
        return True
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="store_true")
    parser.add_argument("--seed-if-empty", action="store_true")
    args = parser.parse_args()
    try:
        api, worker = Settings(), WorkerSettings()
        safe = local_config(api, worker)
        if args.config:
            print(json.dumps(safe))
            return 0
        return 0 if asyncio.run(check(api, args.seed_if_empty)) else 1
    except Exception as exc:  # noqa: BLE001 -- pydantic errors can contain private DSNs
        if type(exc) is ValueError:
            print(str(exc), file=sys.stderr)
        else:
            print(
                f"Local configuration/setup failed ({type(exc).__name__}); inspect .env locally.",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
