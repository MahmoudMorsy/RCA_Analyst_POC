from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from rca_app.config import AppConfig


class ModelRoleConfig(BaseModel):
    provider: str = "openai-compatible"
    endpoint: str = "http://127.0.0.1:1234/v1"
    model: str = ""
    temperature: float = 0.1
    reasoning_effort: str = "provider_default"
    max_tokens: int = 6144
    context_size: Optional[int] = None
    timeout_seconds: int = 10800
    thinking_mode: str = "provider_default"
    transport: str = "auto"
    api_token_env: str = "LM_API_TOKEN"


class InferenceEngineConfig(BaseModel):
    cpu_threads: Optional[int] = None
    gpu_layers: Optional[int] = None
    gpu_offload: Optional[bool] = None
    tensor_split: Optional[str] = None
    flash_attention: Optional[bool] = None
    batch_size: Optional[int] = None
    eval_batch_size: Optional[int] = None
    parallel_slots: Optional[int] = None
    context_size_override: Optional[int] = None
    provider_options: dict[str, Any] = Field(default_factory=dict)


class DeploymentConfig(BaseModel):
    profile_name: str = "Local Dell"
    type: Literal["local", "runpod", "home", "custom"] = "local"
    bind_host: str = "127.0.0.1"
    port: int = 8000
    storage_root: str = ""
    auth_required: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"])
    description: str = ""
    feature_overrides: dict[str, bool] = Field(default_factory=dict)


class ApplicationConfig(BaseModel):
    """Deployment-neutral configuration persisted by the backend.

    `rca` retains the exact v0.8.4 AppConfig field names to minimize semantic
    migration risk. Model locations/provider details and engine settings are
    separated from those RCA behavior settings.
    """

    schema_version: int = 1
    rca: dict[str, Any] = Field(default_factory=dict)
    primary_model: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    small_model: ModelRoleConfig = Field(default_factory=lambda: ModelRoleConfig(temperature=0.0, reasoning_effort="provider_default", max_tokens=6000, thinking_mode="off"))
    inference: InferenceEngineConfig = Field(default_factory=InferenceEngineConfig)

    @classmethod
    def from_legacy(cls, legacy: AppConfig) -> "ApplicationConfig":
        data = asdict(legacy)
        rca = dict(data)
        base_url = rca.pop("base_url", "http://127.0.0.1:1234/v1")
        model = rca.pop("model", "")
        small_model = rca.pop("fast_repair_model", "")
        return cls(
            rca=rca,
            primary_model=ModelRoleConfig(
                provider="openai-compatible",
                endpoint=base_url,
                model=model,
                temperature=legacy.temperature,
                reasoning_effort=legacy.reasoning_effort,
                max_tokens=legacy.max_tokens,
                timeout_seconds=legacy.request_timeout_seconds,
                thinking_mode="provider_default",
                transport="auto",
            ),
            small_model=ModelRoleConfig(
                provider="openai-compatible",
                endpoint=base_url,
                model=small_model,
                temperature=legacy.fast_repair_temperature,
                reasoning_effort=legacy.fast_repair_reasoning_effort,
                max_tokens=legacy.semantic_preparation_max_tokens,
                timeout_seconds=legacy.request_timeout_seconds,
                thinking_mode=legacy.fast_repair_thinking_mode,
                transport=legacy.fast_repair_transport,
            ),
        )

    def to_legacy_app_config(self) -> AppConfig:
        allowed = set(AppConfig.__annotations__)
        payload = {k: v for k, v in self.rca.items() if k in allowed}
        payload.update(
            {
                "base_url": self.primary_model.endpoint,
                "model": self.primary_model.model,
                "temperature": self.primary_model.temperature,
                "reasoning_effort": self.primary_model.reasoning_effort,
                "max_tokens": self.primary_model.max_tokens,
                "request_timeout_seconds": self.primary_model.timeout_seconds,
                "fast_repair_model": self.small_model.model,
                "fast_repair_temperature": self.small_model.temperature,
                "fast_repair_reasoning_effort": self.small_model.reasoning_effort,
                "fast_repair_thinking_mode": self.small_model.thinking_mode,
                "fast_repair_transport": self.small_model.transport,
            }
        )
        return AppConfig(**{k: v for k, v in payload.items() if k in allowed})


class BackendSettings:
    def __init__(self, deployment: DeploymentConfig, config_path: Path):
        self.deployment = deployment
        self.config_path = config_path

    @property
    def storage_root(self) -> Path:
        if self.deployment.storage_root:
            return Path(os.path.expandvars(os.path.expanduser(self.deployment.storage_root))).resolve()
        env = os.environ.get("RCA_STORAGE_ROOT", "").strip()
        if env:
            return Path(os.path.expandvars(os.path.expanduser(env))).resolve()
        return (Path.home() / ".rca_analyst_poc" / "web_backend").resolve()

    @classmethod
    def load(cls, project_root: Path) -> "BackendSettings":
        profile = os.environ.get("RCA_DEPLOYMENT_PROFILE", "local-dell")
        candidate = Path(profile)
        if not candidate.exists():
            candidate = project_root / "configs" / "deployment" / f"{profile}.yaml"
        data: dict[str, Any] = {}
        if candidate.exists():
            data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        deployment = DeploymentConfig.model_validate(data.get("deployment", data or {}))
        storage_root = deployment.storage_root or os.environ.get("RCA_STORAGE_ROOT", "")
        if storage_root:
            deployment.storage_root = storage_root
        config_path = (Path(os.path.expanduser(deployment.storage_root)).resolve() if deployment.storage_root else (Path.home() / ".rca_analyst_poc" / "web_backend")) / "config" / "application.json"
        return cls(deployment, config_path)


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> ApplicationConfig:
        cfg = None
        if self.path.exists():
            try:
                cfg = ApplicationConfig.model_validate_json(self.path.read_text(encoding="utf-8"))
            except Exception:
                cfg = None
        if cfg is None:
            cfg = ApplicationConfig.from_legacy(AppConfig.load())
        # Deployment-time overrides keep container/profile changes out of RCA code.
        if os.environ.get("RCA_PRIMARY_ENDPOINT"):
            cfg.primary_model.endpoint = os.environ["RCA_PRIMARY_ENDPOINT"]
        if os.environ.get("RCA_SMALL_ENDPOINT"):
            cfg.small_model.endpoint = os.environ["RCA_SMALL_ENDPOINT"]
        if os.environ.get("RCA_PRIMARY_MODEL"):
            cfg.primary_model.model = os.environ["RCA_PRIMARY_MODEL"]
        if os.environ.get("RCA_SMALL_MODEL"):
            cfg.small_model.model = os.environ["RCA_SMALL_MODEL"]
        if os.environ.get("RCA_PRIMARY_PROVIDER"):
            cfg.primary_model.provider = os.environ["RCA_PRIMARY_PROVIDER"]
        if os.environ.get("RCA_SMALL_PROVIDER"):
            cfg.small_model.provider = os.environ["RCA_SMALL_PROVIDER"]
        return cfg

    def save(self, config: ApplicationConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
