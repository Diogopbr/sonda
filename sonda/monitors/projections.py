from typing import Any

from sonda.incidents.projections import date, incident_projection


def check_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "monitor_id": str(row["monitor_id"]),
        "state": row["state"],
        "status_code": row["status_code"],
        "duration_ms": row["duration_ms"],
        "error_code": row["error_code"],
        "abandon_reason": row["abandon_reason"],
        "started_at": date(row["started_at"]),
        "finished_at": date(row["finished_at"]),
        "origin": row["origin"],
    }


def monitor_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "target_kind": row["target_kind"],
        "target_url": row["target_url"],
        "interval_seconds": row["interval_seconds"],
        "fixture_mode": row["fixture_mode"],
        "enabled": row["enabled"],
        "observed_state": row["observed_state"],
        "version": row["version"],
        "failure_streak": row["failure_streak"],
        "success_streak": row["success_streak"],
        "last_check": check_payload(row["last_check"]) if row["last_check"] else None,
        "active_incident": incident_projection(row["active_incident"])
        if row["active_incident"]
        else None,
    }
