from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from rca_app import RCA_CORE_VERSION, __version__
from rca_app.model_gateway import ModelClientSpec, ModelGateway

from .api_models import ConfigUpdateRequest, ModelDiscoverRequest, ModelTestRequest, RunCreateRequest, RunState, SessionLoadRequest, SessionSaveRequest
from .auth import AuthGuard
from .backend_config import ApplicationConfig, BackendSettings, ConfigStore
from .run_manager import RunManager, TERMINAL
from .sessions import SessionService
from .storage import LocalStorageBackend, safe_name
from .system_info import SystemInfoService


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def create_app(*, settings: Optional[BackendSettings] = None, run_manager: Optional[RunManager] = None) -> FastAPI:
    root = _project_root()
    settings = settings or BackendSettings.load(root)
    storage = LocalStorageBackend(settings.storage_root)
    config_store = ConfigStore(settings.config_path)
    config_store.path = storage.root / "config" / "application.json"
    system_info = SystemInfoService()
    manager = run_manager or RunManager(
        storage,
        settings,
        config_store,
        system_info=system_info,
        max_workers=int(os.environ.get("RCA_MAX_CONCURRENT_RUNS", "1") or "1"),
    )
    sessions = manager.sessions
    gateway = ModelGateway()
    auth = AuthGuard(settings)

    app = FastAPI(
        title="RCA Analyst Backend",
        version=__version__,
        description="Stable backend API for the hardware-independent Automotive AI RCA application.",
    )
    app.state.settings = settings
    app.state.storage = storage
    app.state.config_store = config_store
    app.state.run_manager = manager

    origins = list(settings.deployment.cors_origins)
    env_origins = os.environ.get("RCA_CORS_ORIGINS", "").strip()
    if env_origins:
        origins = [x.strip() for x in env_origins.split(",") if x.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )

    api = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/api/v1/health", dependencies=[Depends(auth)])
    async def health():
        return {
            "status": "ok",
            "backend_version": __version__,
            "core_version": RCA_CORE_VERSION,
            "deployment": settings.deployment.type,
            "profile_name": settings.deployment.profile_name,
        }

    @app.get("/api/v1/system", dependencies=[Depends(auth)])
    async def system():
        return system_info.snapshot(storage.root)

    def _model_spec(role: str, cfg: ApplicationConfig, item_override=None):
        item = item_override or (cfg.primary_model if role == "primary" else cfg.small_model)
        token = os.environ.get(item.api_token_env or "", "") if item.api_token_env else ""
        return ModelClientSpec(
            role=role,
            provider=item.provider,
            base_url=item.endpoint,
            model=item.model,
            temperature=item.temperature,
            reasoning_effort=item.reasoning_effort,
            max_tokens=item.max_tokens,
            timeout_seconds=min(item.timeout_seconds, 15),
            api_token=token,
            thinking_mode=item.thinking_mode,
            transport=item.transport,
        )

    def _capabilities(cfg: ApplicationConfig) -> dict[str, Any]:
        snap = system_info.snapshot(storage.root)
        # v1.8.11 does not own the lifecycle of external LM Studio/llama.cpp/vLLM
        # processes. Engine controls therefore remain visible as deployment
        # metadata but are capability-disabled unless a future deployment
        # adapter explicitly declares that the backend manages that setting.
        features = {
            "flash_attention": False,
            "tensor_split": False,
            "gpu_offload": False,
            "parallel_inference": False,
            "cpu_threads": False,
            "batch_size": False,
            "eval_batch_size": False,
            "context_override": False,
        }
        features.update(settings.deployment.feature_overrides)
        available = {"primary": False, "small": False, "large_model": False}
        configured = {"primary": bool(cfg.primary_model.model), "small": bool(cfg.small_model.model)}
        # Capability discovery is observational; an unavailable model server must
        # not make /capabilities itself fail.
        for role in ("primary", "small"):
            item = cfg.primary_model if role == "primary" else cfg.small_model
            if not item.model:
                continue
            try:
                models = gateway.list_models(_model_spec(role, cfg))
                available[role] = item.model in models or bool(models)
            except Exception:
                available[role] = False
        return {
            "deployment": settings.deployment.type,
            "profile_name": settings.deployment.profile_name,
            "backend_version": __version__,
            "gpu_count": snap.get("gpu_count", 0),
            "gpus": snap.get("gpus", []),
            "features": features,
            "models": available,
            "configured_models": configured,
            "auth_required": settings.deployment.auth_required,
            "storage_root": str(storage.root),
            "environment_overrides": config_store.environment_overrides(),
        }

    @app.get("/api/v1/capabilities", dependencies=[Depends(auth)])
    async def capabilities():
        return _capabilities(config_store.load())

    @app.get("/api/v1/models", dependencies=[Depends(auth)])
    async def models(refresh: bool = Query(default=False)):
        cfg = config_store.load()
        out = {}
        for role in ("primary", "small"):
            item = cfg.primary_model if role == "primary" else cfg.small_model
            try:
                listed = gateway.list_models(_model_spec(role, cfg))
                out[role] = {"status": "AVAILABLE", "configured": item.model, "models": listed}
            except Exception as exc:
                out[role] = {"status": "UNAVAILABLE", "configured": item.model, "models": [], "error": str(exc)}
        return out

    @app.post("/api/v1/models/discover", dependencies=[Depends(auth)])
    async def discover_model(request: ModelDiscoverRequest):
        cfg = config_store.load()
        try:
            spec = _model_spec(request.role, cfg, request.config)
            catalog = gateway.model_catalog(spec)
            return {
                "role": request.role,
                "status": "AVAILABLE",
                "endpoint": request.config.endpoint,
                "configured": request.config.model,
                "models": [str(x.get("id")) for x in catalog if x.get("id")],
                "catalog": catalog,
            }
        except Exception as exc:
            return {
                "role": request.role,
                "status": "UNAVAILABLE",
                "endpoint": request.config.endpoint,
                "configured": request.config.model,
                "models": [],
                "catalog": [],
                "error": str(exc),
            }

    @app.post("/api/v1/models/test", dependencies=[Depends(auth)])
    async def test_model(request: ModelTestRequest):
        cfg = config_store.load()
        item = request.config or (cfg.primary_model if request.role == "primary" else cfg.small_model)
        try:
            spec = _model_spec(request.role, cfg, item)
            ok, message = gateway.test_connection(spec)
            catalog = gateway.model_catalog(spec)
            return {"role": request.role, "ok": ok, "message": message, "endpoint": item.endpoint, "model": item.model, "catalog": catalog}
        except Exception as exc:
            return {"role": request.role, "ok": False, "message": str(exc), "endpoint": item.endpoint, "model": item.model, "catalog": []}

    @app.get("/api/v1/config", dependencies=[Depends(auth)])
    async def get_config():
        return config_store.load().model_dump(mode="json")

    @app.put("/api/v1/config", dependencies=[Depends(auth)])
    async def put_config(request: ConfigUpdateRequest):
        cfg = request.config
        caps = _capabilities(cfg)
        feature_for = {
            "gpu_offload": "gpu_offload",
            "tensor_split": "tensor_split",
            "flash_attention": "flash_attention",
            "parallel_slots": "parallel_inference",
            "batch_size": "batch_size",
            "eval_batch_size": "eval_batch_size",
            "context_size_override": "context_override",
        }
        unsupported = []
        values = cfg.inference.model_dump(mode="json")
        for field, feature in feature_for.items():
            value = values.get(field)
            if value not in (None, "", False) and not caps["features"].get(feature, False):
                unsupported.append({"field": field, "capability": feature})
        if unsupported:
            raise HTTPException(status_code=422, detail={"message": "Unsupported inference parameter(s) for this backend", "unsupported": unsupported})
        config_store.save(cfg)
        return cfg.model_dump(mode="json")

    @app.post("/api/v1/files", dependencies=[Depends(auth)])
    async def upload_file(file: UploadFile = File(...)):
        data = await file.read()
        return storage.save_upload(file.filename or "upload.bin", data)

    @app.get("/api/v1/files/{file_id}", dependencies=[Depends(auth)])
    async def download_file(file_id: str):
        try:
            path, meta = storage.get_upload(file_id)
        except Exception:
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path, filename=meta["filename"])

    @app.get("/api/v1/examples/{case_id}", dependencies=[Depends(auth)])
    async def get_example(case_id: str):
        name = safe_name(case_id).upper()
        if name not in {"TEST-001", "TEST-002", "TEST-003"}:
            raise HTTPException(status_code=404, detail="Example not found")
        path = root / "examples" / f"{name}.txt"
        return {"case_id": name, "raw_case": path.read_text(encoding="utf-8")}

    @app.post("/api/v1/runs", dependencies=[Depends(auth)])
    async def create_run(request: RunCreateRequest):
        try:
            summary = manager.create(request)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"run_id": summary.run_id, "status": summary.status.value}

    @app.get("/api/v1/runs", dependencies=[Depends(auth)])
    async def list_runs():
        return [x.model_dump(mode="json") for x in manager.list_runs()]

    @app.get("/api/v1/runs/{run_id}", dependencies=[Depends(auth)])
    async def get_run(run_id: str):
        try:
            return manager.get_summary(run_id).model_dump(mode="json")
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found")

    @app.get("/api/v1/runs/{run_id}/status", dependencies=[Depends(auth)])
    async def get_run_status(run_id: str):
        try:
            return manager.get_summary(run_id).model_dump(mode="json")
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found")

    @app.get("/api/v1/runs/{run_id}/pipeline", dependencies=[Depends(auth)])
    async def get_pipeline(run_id: str):
        try: return manager.get_pipeline(run_id)
        except Exception: raise HTTPException(status_code=404, detail="Run not found")

    @app.get("/api/v1/runs/{run_id}/metrics", dependencies=[Depends(auth)])
    async def get_metrics(run_id: str):
        try: return manager.get_metrics(run_id)
        except Exception: raise HTTPException(status_code=404, detail="Metrics not found")

    @app.get("/api/v1/runs/{run_id}/logs", dependencies=[Depends(auth)])
    async def get_logs(run_id: str):
        try: return manager.get_logs(run_id)
        except Exception: raise HTTPException(status_code=404, detail="Run not found")

    @app.get("/api/v1/runs/{run_id}/result", dependencies=[Depends(auth)])
    async def get_result(run_id: str):
        try: return manager.get_result(run_id)
        except Exception: raise HTTPException(status_code=404, detail="Run not found")

    @app.post("/api/v1/runs/{run_id}/cancel", dependencies=[Depends(auth)])
    async def cancel_run(run_id: str):
        try:
            return manager.cancel(run_id).model_dump(mode="json")
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found")

    @app.get("/api/v1/runs/{run_id}/events", dependencies=[Depends(auth)])
    async def run_events(run_id: str, after: int = Query(default=0, ge=0)):
        try:
            manager.get_summary(run_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Run not found")

        async def generate():
            cursor = after
            idle = 0
            while True:
                events = manager.get_events(run_id, cursor)
                if events:
                    idle = 0
                    for event in events:
                        cursor = max(cursor, int(event["id"]))
                        yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                else:
                    idle += 1
                    if idle % 15 == 0:
                        yield ": keepalive\n\n"
                summary = manager.get_summary(run_id)
                if summary.status in TERMINAL and not manager.get_events(run_id, cursor):
                    yield f"event: terminal\ndata: {json.dumps({'status': summary.status.value})}\n\n"
                    break
                await asyncio.sleep(1.0)
        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/v1/runs/{run_id}/report/download", dependencies=[Depends(auth)])
    async def report_download(run_id: str):
        path = storage.path(f"runs/{run_id}/report.md")
        if not path.exists(): raise HTTPException(status_code=404, detail="Report not available")
        return FileResponse(path, filename=f"{run_id}-RCA_Report_v{__version__}.md", media_type="text/markdown")

    @app.get("/api/v1/runs/{run_id}/session/download", dependencies=[Depends(auth)])
    async def run_session_download(run_id: str):
        summary = manager.get_summary(run_id)
        if not summary.session_id: raise HTTPException(status_code=404, detail="Session not available")
        path = storage.path(f"sessions/{summary.session_id}.json")
        return FileResponse(path, filename=f"{run_id}-RCA_Session_v{__version__}.json", media_type="application/json")

    @app.post("/api/v1/sessions/save", dependencies=[Depends(auth)])
    async def save_session(request: SessionSaveRequest):
        summary = manager.get_summary(request.run_id)
        existing = sessions.load(summary.session_id) if summary.session_id else None
        if existing is None:
            raise HTTPException(status_code=409, detail="Run session has not been finalized yet")
        if request.session_id and request.session_id != summary.session_id:
            existing = dict(existing)
            existing["session_id"] = request.session_id
            sid = sessions.save(existing)
        else:
            sid = summary.session_id
        return {"session_id": sid}

    @app.post("/api/v1/sessions/load", dependencies=[Depends(auth)])
    async def load_session(request: SessionLoadRequest):
        payload = request.payload
        if payload is None and request.file_id:
            path, _meta = storage.get_upload(request.file_id)
            payload = json.loads(path.read_text(encoding="utf-8"))
        if payload is None:
            raise HTTPException(status_code=422, detail="Provide file_id or payload")
        migrated = sessions.migrate_legacy(
            payload,
            deployment=settings.deployment.model_dump(mode="json"),
            hardware=system_info.snapshot(storage.root),
            inference_engine={"provider": config_store.load().primary_model.provider},
        )
        sid = sessions.save(migrated)
        return {"session_id": sid, "session": sessions.load(sid)}

    @app.get("/api/v1/sessions", dependencies=[Depends(auth)])
    async def list_sessions():
        return sessions.list()

    @app.get("/api/v1/sessions/{session_id}", dependencies=[Depends(auth)])
    async def get_session(session_id: str):
        try: return sessions.load(session_id)
        except Exception: raise HTTPException(status_code=404, detail="Session not found")

    @app.get("/api/v1/sessions/{session_id}/download", dependencies=[Depends(auth)])
    async def session_download(session_id: str):
        path = storage.path(f"sessions/{safe_name(session_id)}.json")
        if not path.exists(): raise HTTPException(status_code=404, detail="Session not found")
        return FileResponse(path, filename=f"{safe_name(session_id)}.json", media_type="application/json")

    web_dir = root / "web"
    if web_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(web_dir)), name="assets")

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return (web_dir / "index.html").read_text(encoding="utf-8")

    return app


app = create_app()
