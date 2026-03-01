from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HISTORY_DIR = Path("output/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_snapshot(payload: dict[str, Any]) -> str:
    run_id = f"run_{_ts()}"
    path = HISTORY_DIR / f"{run_id}.json"

    data = {
        "run_id": run_id,
        "created_at_utc": _ts(),
        "status": "pending",
        "payload": payload,
        "error": None,
        "pdf_path": None,
    }

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_id


def update_snapshot(
    run_id: str,
    *,
    status: str,
    error: str | None = None,
    pdf_path: str | None = None,
) -> None:
    path = HISTORY_DIR / f"{run_id}.json"
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = status
    data["error"] = error
    data["pdf_path"] = pdf_path
    data["updated_at_utc"] = _ts()

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_snapshots(limit: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for snapshot_file in sorted(HISTORY_DIR.glob("run_*.json"), reverse=True):
        try:
            items.append(json.loads(snapshot_file.read_text(encoding="utf-8")))
        except Exception:
            continue

        if len(items) >= limit:
            break

    return items


def load_payload(run_id: str) -> dict[str, Any] | None:
    path = HISTORY_DIR / f"{run_id}.json"
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None
