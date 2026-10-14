from dataclasses import dataclass

from sonda.db import Database


@dataclass(frozen=True)
class CleanupReport:
    workspaces: int = 0
    sessions: int = 0
    limits: int = 0
    skipped: bool = False


async def collect_expired(
    db: Database, *, batch: int = 10, throttled: bool = True
) -> CleanupReport:
    if not 1 <= batch <= 1000:
        raise ValueError("Cleanup batch must be between1 and1000")
    async with db.transaction() as connection:
        maintenance = await (
            await connection.execute(
                "SELECT last_cleanup_at IS NULL OR "
                "last_cleanup_at<clock_timestamp()-interval '1 minute' AS due "
                "FROM maintenance WHERE id=true FOR UPDATE SKIP LOCKED"
            )
        ).fetchone()
        if maintenance is None or (throttled and not maintenance["due"]):
            return CleanupReport(skipped=True)
        workspaces = await (
            await connection.execute(
                "WITH victims AS (SELECT id FROM workspaces WHERE kind='demo' "
                "AND (revoked_at IS NOT NULL OR expires_at<=clock_timestamp()) "
                "ORDER BY expires_at LIMIT %s FOR UPDATE SKIP LOCKED) "
                "DELETE FROM workspaces w USING victims v WHERE w.id=v.id RETURNING w.id",
                (batch,),
            )
        ).fetchall()
        sessions = await (
            await connection.execute(
                "WITH victims AS (SELECT id FROM sessions WHERE expires_at<=clock_timestamp() "
                "ORDER BY expires_at LIMIT %s FOR UPDATE SKIP LOCKED) "
                "DELETE FROM sessions s USING victims v WHERE s.id=v.id RETURNING s.id",
                (batch,),
            )
        ).fetchall()
        limits = await (
            await connection.execute(
                "WITH victims AS (SELECT key,bucket FROM rate_limits "
                "WHERE expires_at<=clock_timestamp() ORDER BY expires_at "
                "LIMIT %s FOR UPDATE SKIP LOCKED) DELETE FROM rate_limits r "
                "USING victims v WHERE r.key=v.key AND r.bucket=v.bucket RETURNING r.key",
                (batch,),
            )
        ).fetchall()
        await connection.execute(
            "UPDATE maintenance SET last_cleanup_at=clock_timestamp() WHERE id=true"
        )
    return CleanupReport(len(workspaces), len(sessions), len(limits))
