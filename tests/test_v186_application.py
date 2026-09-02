from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from rca_app.cancellation import CancellationToken
from rca_server.app import create_app
from rca_server.backend_config import (
    ApplicationConfig,
    BackendSettings,
    ConfigStore,
    DeploymentConfig,
    ModelRoleConfig,
    ModelRoutingConfig,
)
from rca_server.pipeline_factory import PipelineFactory
from rca_server.run_manager import RunManager
from rca_server.storage import LocalStorageBackend


class ClientStub:
    def __init__(self, spec):
        self.base_url = spec.base_url
        self.model = spec.model
        self.temperature = spec.temperature
        self.reasoning_effort = spec.reasoning_effort
        self.max_tokens = spec.max_tokens
        self.timeout_seconds = spec.timeout_seconds
        self.thinking_mode = spec.thinking_mode
        self.transport = spec.transport

    def resolve_transport(self):
        return self.transport


class RecordingGateway:
    def __init__(self):
        self.specs = []

    def create_client(self, spec, *, cancellation_token=None):
        self.specs.append(spec)
        return ClientStub(spec)


class TraceMergeResult:
    final_report = "# report"

    def model_dump(self, mode="json"):
        return {
            "canonical_case": {"ticket_id": "TRACE"},
            "validated": {"issues": [], "requirement_results": []},
            "final_report": self.final_report,
            "stats": [],
            "attempts": [],
            "repair_log": [],
        }


class TraceMergePipeline:
    def __init__(self, token):
        self.token = token

    def cancel(self, reason="stop"):
        self.token.cancel(reason)

    def run(self, raw_case, progress=None, trace=None):
        trace = trace or (lambda *_: None)
        trace({
            "stage_id": "09_verified_semantics",
            "title": "Verified Semantic Representation",
            "status": "running",
            "summary": "working",
            "input_text": '{"source":"keep-me"}',
            "input_data": {"source": "keep-me"},
            "output_text": "",
        })
        trace({
            "stage_id": "09_verified_semantics",
            "title": "Verified Semantic Representation",
            "status": "complete",
            "summary": "done",
            "input_text": "",
            "output_text": '{"verified":true}',
            "output_data": {"verified": True},
        })
        return TraceMergeResult()


class TraceMergeFactory:
    def build(self, config, cancellation_token):
        return TraceMergePipeline(cancellation_token)


def _wait(client, run_id, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        obj = client.get(f"/api/v1/runs/{run_id}/status").json()
        if obj["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return obj
        time.sleep(0.01)
    raise AssertionError("run did not finish")


def _stack(tmp_path, factory=None):
    dep = DeploymentConfig(profile_name="Test", type="local", storage_root=str(tmp_path), cors_origins=[])
    settings = BackendSettings(dep, tmp_path / "config" / "application.json")
    storage = LocalStorageBackend(tmp_path)
    store = ConfigStore(tmp_path / "config" / "application.json")
    manager = RunManager(storage, settings, store, pipeline_factory=factory or TraceMergeFactory(), max_workers=1)
    return create_app(settings=settings, run_manager=manager), manager


def test_v186_critical_semantic_roles_can_route_to_primary_without_changing_utility_model():
    gateway = RecordingGateway()
    cfg = ApplicationConfig(
        rca={
            "fast_intake_enabled": True,
            "fast_repair_enabled": True,
            "fast_hypothesis_review_enabled": True,
            "fast_final_review_enabled": False,
            "semantic_preparation_enabled": True,
        },
        primary_model=ModelRoleConfig(endpoint="http://primary:8003/v1", model="qwen-27b", max_tokens=12000),
        small_model=ModelRoleConfig(endpoint="http://small:8004/v1", model="qwen-4b", max_tokens=6000, temperature=0.0, thinking_mode="off"),
        model_routing=ModelRoutingConfig(
            semantic_preparation_role="primary",
            semantic_verification_role="primary",
            semantic_preparation_thinking_mode="off",
            semantic_verification_thinking_mode="off",
        ),
    )
    pipeline = PipelineFactory(gateway).build(cfg, CancellationToken())
    assert pipeline.semantic_preparation_client.model == "qwen-27b"
    assert pipeline.semantic_preparation_client.base_url == "http://primary:8003/v1"
    assert pipeline.semantic_verification_client.model == "qwen-27b"
    assert pipeline.semantic_verification_client.base_url == "http://primary:8003/v1"
    # Utility/intake remains on the configured small model.
    assert pipeline.intake_client.model == "qwen-4b"
    assert pipeline.intake_client.base_url == "http://small:8004/v1"


def test_v186_compiler_and_verifier_can_use_different_model_roles():
    gateway = RecordingGateway()
    cfg = ApplicationConfig(
        rca={"fast_intake_enabled": False, "fast_repair_enabled": False, "fast_hypothesis_review_enabled": False},
        primary_model=ModelRoleConfig(endpoint="http://primary:8003/v1", model="qwen-27b"),
        small_model=ModelRoleConfig(endpoint="http://small:8004/v1", model="qwen-4b"),
        model_routing=ModelRoutingConfig(
            semantic_preparation_role="small",
            semantic_verification_role="primary",
        ),
    )
    pipeline = PipelineFactory(gateway).build(cfg, CancellationToken())
    assert pipeline.semantic_preparation_client.model == "qwen-4b"
    assert pipeline.semantic_verification_client.model == "qwen-27b"


def test_v186_stage_merge_preserves_past_input_and_structured_io(tmp_path):
    app, _ = _stack(tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "trace"}).json()["run_id"]
    _wait(client, run_id)
    stages = client.get(f"/api/v1/runs/{run_id}/pipeline").json()
    assert len(stages) == 1
    stage = stages[0]
    assert stage["input_text"] == '{"source":"keep-me"}'
    assert stage["input_data"] == {"source": "keep-me"}
    assert stage["output_data"] == {"verified": True}
    assert stage["status"] == "COMPLETE"


def test_v186_model_discovery_uses_current_form_endpoint_without_saving(tmp_path, monkeypatch):
    captured = []

    def fake_catalog(self, spec):
        captured.append((spec.base_url, spec.model))
        return [{"id": "model-from-current-endpoint", "meta": {"n_ctx": 32768}}]

    monkeypatch.setattr("rca_server.app.ModelGateway.model_catalog", fake_catalog)
    app, _ = _stack(tmp_path)
    client = TestClient(app)
    role_cfg = ModelRoleConfig(endpoint="http://current-form:9000/v1", model="old-value").model_dump(mode="json")
    resp = client.post("/api/v1/models/discover", json={"role": "small", "config": role_cfg})
    assert resp.status_code == 200
    data = resp.json()
    assert captured == [("http://current-form:9000/v1", "old-value")]
    assert data["models"] == ["model-from-current-endpoint"]
    assert data["catalog"][0]["meta"]["n_ctx"] == 32768


def test_v186_config_reports_environment_overrides_instead_of_silently_hiding_them(tmp_path, monkeypatch):
    monkeypatch.setenv("RCA_SMALL_ENDPOINT", "http://env-small:8004/v1")
    monkeypatch.setenv("RCA_SMALL_MODEL", "env-model")
    app, _ = _stack(tmp_path)
    client = TestClient(app)
    caps = client.get("/api/v1/capabilities").json()
    assert caps["environment_overrides"]["small_model.endpoint"]["value"] == "http://env-small:8004/v1"
    assert caps["environment_overrides"]["small_model.model"]["value"] == "env-model"


def test_v186_frontend_contains_human_readable_renderer_batch_case_selector_and_current_endpoint_discovery():
    root = Path(__file__).resolve().parent.parent
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    for token in ("Critical Semantic Model Routing", "Discover at Endpoint", "batchCaseSelect", "modelOverrideWarning"):
        assert token in html
    for token in ("renderStructured", "/models/discover", "selectedCaseId", "config_override"):
        assert token in js
