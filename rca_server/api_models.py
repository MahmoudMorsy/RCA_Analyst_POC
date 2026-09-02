from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .backend_config import ApplicationConfig, InferenceEngineConfig, ModelRoleConfig


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunState(str, Enum):
    QUEUED = "QUEUED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunCreateRequest(BaseModel):
    run_type: Literal["single", "builtin_regression", "bundle"] = "single"
    raw_case: str = ""
    file_id: str = ""
    label: str = ""
    config_override: Optional[ApplicationConfig] = None


class RunCreateResponse(BaseModel):
    run_id: str
    status: RunState


class PipelineStage(BaseModel):
    stage_id: str
    name: str
    status: str
    summary: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    elapsed_ms: Optional[float] = None
    input_text: str = ""
    output_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    run_id: str
    run_type: str
    label: str = ""
    status: RunState
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_stage: str = ""
    progress_detail: str = ""
    error: str = ""
    session_id: str = ""


class BackendProfile(BaseModel):
    id: str
    name: str
    backend_url: str
    description: str = ""
    auth_method: Literal["none", "bearer"] = "none"
    model_endpoint_override: str = ""
    auto_connect: bool = False


class SessionSaveRequest(BaseModel):
    run_id: str
    session_id: str = ""


class SessionLoadRequest(BaseModel):
    file_id: str = ""
    payload: Optional[dict[str, Any]] = None


class ModelTestRequest(BaseModel):
    role: Literal["primary", "small"] = "primary"


class ConfigUpdateRequest(BaseModel):
    config: ApplicationConfig
