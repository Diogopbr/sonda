from datetime import datetime
from typing import Any


def date(value: datetime | str | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def incident_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "monitor_id": str(row["monitor_id"]),
        "state": row["state"],
        "version": row["version"],
        "first_failure_at": date(row["first_failure_at"]),
        "confirmed_at": date(row["confirmed_at"]),
        "first_failure_check_id": str(row["first_failure_check_id"]),
        "confirmation_check_id": str(row["confirmation_check_id"]),
        "resolved_at": date(row["resolved_at"]),
        "resolution_check_id": str(row["resolution_check_id"])
        if row["resolution_check_id"]
        else None,
        "acknowledged_at": date(row["acknowledged_at"]),
        "acknowledgement": row["acknowledgement"],
        "acknowledged_by": {"id": str(row["acknowledged_by"]), "name": row.get("actor_name")}
        if row["acknowledged_by"]
        else None,
    }
