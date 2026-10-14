import hashlib
from typing import Any

from psycopg import AsyncConnection

from sonda.http.errors import HttpError


def ip_key(prefix: str, ip: str) -> str:
    return f"{prefix}:{hashlib.sha256(ip.encode('utf-8')).hexdigest()}"


async def lock_key(connection: AsyncConnection[dict[str, Any]], key: str) -> None:
    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':' || %s,0))", (key,)
    )


async def consume_limit(
    connection: AsyncConnection[dict[str, Any]], key: str, seconds: int, maximum: int
) -> None:
    result = await (
        await connection.execute(
            "WITH tick AS MATERIALIZED (SELECT clock_timestamp() AS now), "
            "period AS (SELECT to_timestamp(floor(extract(epoch FROM now)/%s)*%s) AS start "
            "FROM tick) INSERT INTO rate_limits(key,bucket,hits,expires_at) "
            "SELECT %s,start,1,start+%s*interval '1 second' FROM period "
            "ON CONFLICT(key,bucket) DO UPDATE SET hits=rate_limits.hits+1 "
            "RETURNING hits,greatest(1,ceil(extract(epoch FROM "
            "expires_at-(SELECT now FROM tick))))::int AS retry_after",
            (seconds, seconds, key, seconds),
        )
    ).fetchone()
    if result is None:
        raise RuntimeError("Rate counter returned no result")
    if result["hits"] > maximum:
        raise HttpError(
            429,
            "RATE_LIMITED",
            "Limite temporário atingido. Aguarde antes de tentar novamente.",
            retry_after=int(result["retry_after"]),
        )
