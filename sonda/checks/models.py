from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

CheckState = Literal["pending", "finished", "abandoned"]


@dataclass(frozen=True)
class Claim:
    id: str
    workspace_id: str
    monitor_id: str
    lease_token: str = field(repr=False)
    claimed_at: datetime
    lease_until: datetime
    replayed: bool
    state: CheckState


@dataclass(frozen=True)
class CheckProjection:
    id: str
    monitor_id: str
    state: CheckState
    status_code: int | None
    duration_ms: int | None
    error_code: str | None
    abandon_reason: str | None
    started_at: datetime
    finished_at: datetime | None
    origin: Literal["manual", "runner"] = "manual"


def claim_projection(row: dict[str, Any], *, replayed: bool) -> Claim:
    return Claim(
        str(row["id"]),
        str(row["workspace_id"]),
        str(row["monitor_id"]),
        str(row["lease_token"]),
        row["started_at"],
        row["lease_until"],
        replayed,
        row["state"],
    )


def check_projection(row: dict[str, Any]) -> CheckProjection:
    return CheckProjection(
        str(row["id"]),
        str(row["monitor_id"]),
        row["state"],
        row["status_code"],
        row["duration_ms"],
        row["error_code"],
        row["abandon_reason"],
        row["started_at"],
        row["finished_at"],
        row["origin"],
    )
