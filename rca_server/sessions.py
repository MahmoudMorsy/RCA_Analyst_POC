from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from rca_app import __version__

from .storage import LocalStorageBackend, safe_name


SESSION_SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionService:
    def __init__(self, storage: LocalStorageBackend):
        self.storage = storage

    def make_envelope(
        self,
        *,
        session_id: str,
        run_id: str,
        status: str,
        payload: dict[str, Any],
        config_snapshot: dict[str, Any],
        deployment: dict[str, Any],
        hardware: dict[str, Any],
        inference_engine: dict[str, Any],
        original_legacy_payload: Optional[dict[str, Any]] = None,
        migration: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        out = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "app_version": __version__,
            "session_id": session_id,
            "run_id": run_id,
            "status": status,
            "created_at": _now(),
            "deployment": deployment,
            "hardware": hardware,
            "inference_engine": inference_engine,
            "config_snapshot": config_snapshot,
            "payload": payload,
        }
        if original_legacy_payload is not None:
            out["original_legacy_payload"] = original_legacy_payload
        if migration:
            out["migration"] = migration
        return out

    def save(self, envelope: dict[str, Any]) -> str:
        session_id = safe_name(str(envelope.get("session_id") or uuid4().hex), "session")
        envelope = dict(envelope)
        envelope["session_id"] = session_id
        self.storage.write_json(f"sessions/{session_id}.json", envelope)
        return session_id

    def load(self, session_id: str) -> dict[str, Any]:
        return self.storage.read_json(f"sessions/{safe_name(session_id)}.json")

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for path in sorted((self.storage.root / "sessions").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = self.storage.read_json(f"sessions/{path.name}")
                rows.append({k: data.get(k) for k in ("session_id", "run_id", "status", "created_at", "app_version", "schema_version")})
            except Exception:
                continue
        return rows

    def migrate_legacy(self, payload: dict[str, Any], *, deployment: dict[str, Any], hardware: dict[str, Any], inference_engine: dict[str, Any]) -> dict[str, Any]:
        if int(payload.get("schema_version") or 0) >= SESSION_SCHEMA_VERSION and "payload" in payload:
            return payload
        status = "FAILED" if payload.get("status") == "FAILED" or "message" in payload and "validated" in payload else "COMPLETED"
        session_id = f"legacy_{uuid4().hex[:12]}"
        return self.make_envelope(
            session_id=session_id,
            run_id=str(payload.get("run_id") or ""),
            status=status,
            payload=payload,
            config_snapshot={},
            deployment=deployment,
            hardware=hardware,
            inference_engine=inference_engine,
            original_legacy_payload=payload,
            migration={
                "from_schema_version": payload.get("schema_version", 0),
                "to_schema_version": SESSION_SCHEMA_VERSION,
                "strategy": "wrapped_without_field_loss",
            },
        )
