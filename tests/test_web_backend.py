from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from rca_app.cancellation import CancellationToken
from rca_server.app import create_app
from rca_server.api_models import RunState
from rca_server.backend_config import BackendSettings, ConfigStore, DeploymentConfig
from rca_server.run_manager import RunManager
from rca_server.storage import LocalStorageBackend


class FakeResult:
    def __init__(self, raw: str):
        self.final_report = f"# Fake RCA Report\n\n{raw}"
        self._payload = {
            "canonical_case": {"ticket_id": "FAKE", "requirements": []},
            "validated": {"semantic": {"affected_functionality": "Fake"}, "issues": [], "requirement_results": []},
            "final_report": self.final_report,
            "stats": [{"elapsed_seconds": 0.1, "prompt_tokens": 10, "completion_tokens": 5, "reasoning_tokens": 0, "total_tokens": 15, "retries": 0, "endpoint": "fake", "model": "fake-model"}],
            "attempts": [{"call_index": 1, "stage": "fake", "model_role": "PRIMARY", "finish_reason": "stop", "transport": "fake"}],
            "repair_log": [],
        }

    def model_dump(self, mode="json"):
        return self._payload


class FakePipeline:
    def __init__(self, token: CancellationToken):
        self.token = token

    def cancel(self, reason="Stopped"):
        self.token.cancel(reason)

    def run(self, raw_case, progress=None, trace=None):
        progress = progress or (lambda *_: None)
        trace = trace or (lambda *_: None)
        trace({"stage_id": "01", "title": "Fake Stage", "status": "running", "summary": "working", "input_text": raw_case, "output_text": ""})
        progress("Fake Stage", "working")
        if "SLOW" in raw_case:
            for _ in range(80):
                self.token.throw_if_cancelled("fake slow stage")
                time.sleep(0.005)
        if "PROVIDER_FAIL" in raw_case:
            raise RuntimeError("simulated provider failure")
        self.token.throw_if_cancelled("fake completion")
        trace({"stage_id": "01", "title": "Fake Stage", "status": "complete", "summary": "done", "input_text": raw_case, "output_text": "ok"})
        return FakeResult(raw_case)


class FakePipelineFactory:
    def build(self, config, cancellation_token):
        return FakePipeline(cancellation_token)


def make_stack(tmp_path, deployment=None):
    deployment = deployment or DeploymentConfig(profile_name="Test Local", type="local", storage_root=str(tmp_path), auth_required=False, cors_origins=[])
    settings = BackendSettings(deployment, tmp_path / "config" / "application.json")
    storage = LocalStorageBackend(tmp_path)
    store = ConfigStore(tmp_path / "config" / "application.json")
    manager = RunManager(storage, settings, store, pipeline_factory=FakePipelineFactory(), max_workers=1)
    app = create_app(settings=settings, run_manager=manager)
    return app, manager, storage


def wait_terminal(client, run_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/v1/runs/{run_id}/status").json()
        if data["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return data
        time.sleep(0.02)
    raise AssertionError("run did not become terminal")


def test_health_config_and_frontend_load(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["backend_version"] == "1.8.5"
    assert client.get("/api/v1/config").status_code == 200
    html = client.get("/").text
    for token in ("Backend Profile Details", "Analyze Case", "Live Pipeline", "RCA Configuration", "Stop / Abort", "Run History / Benchmarking"):
        assert token in html


def test_single_run_is_async_persistent_and_reconnectable(tmp_path):
    app, _, storage = make_stack(tmp_path)
    client = TestClient(app)
    created = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "Ticket ID: TC-WEB\nhello"})
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    assert created.json()["status"] == "QUEUED"
    terminal = wait_terminal(client, run_id)
    assert terminal["status"] == "COMPLETED"
    # A new browser/client can reconstruct state from the backend.
    reconnect = TestClient(app).get(f"/api/v1/runs/{run_id}/status").json()
    assert reconnect["status"] == "COMPLETED"
    assert storage.path(f"runs/{run_id}/metadata.json").exists()
    assert client.get(f"/api/v1/runs/{run_id}/pipeline").json()[0]["name"] == "Fake Stage"
    assert client.get(f"/api/v1/runs/{run_id}/result").json()["result"]["final_report"].startswith("# Fake RCA Report")


def test_cancel_preserves_cancelled_run(tmp_path):
    app, _, storage = make_stack(tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "SLOW"}).json()["run_id"]
    deadline = time.time() + 2
    while time.time() < deadline:
        status = client.get(f"/api/v1/runs/{run_id}/status").json()["status"]
        if status == "RUNNING":
            break
        time.sleep(0.01)
    response = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert response.status_code == 200
    terminal = wait_terminal(client, run_id)
    assert terminal["status"] == "CANCELLED"
    assert storage.path(f"runs/{run_id}/metadata.json").exists()
    assert client.get(f"/api/v1/runs/{run_id}/logs").status_code == 200


def test_failed_provider_is_persisted_not_lost(tmp_path):
    app, _, storage = make_stack(tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "PROVIDER_FAIL"}).json()["run_id"]
    terminal = wait_terminal(client, run_id)
    assert terminal["status"] == "FAILED"
    result = client.get(f"/api/v1/runs/{run_id}/result").json()
    assert "simulated provider failure" in result["failure"]["message"]
    assert storage.path(f"runs/{run_id}/failure.json").exists()


def test_file_upload_bundle_contract(tmp_path):
    app, _, storage = make_stack(tmp_path)
    client = TestClient(app)
    resp = client.post("/api/v1/files", files={"file": ("case.zip", b"abc", "application/zip")})
    assert resp.status_code == 200
    meta = resp.json()
    path, stored = storage.get_upload(meta["file_id"])
    assert path.read_bytes() == b"abc"
    assert stored["filename"] == "case.zip"


def test_session_autosave_download_and_legacy_migration(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "session"}).json()["run_id"]
    summary = wait_terminal(client, run_id)
    assert summary["session_id"]
    downloaded = client.get(f"/api/v1/runs/{run_id}/session/download")
    assert downloaded.status_code == 200
    assert downloaded.json()["schema_version"] == 2

    legacy = {"canonical_case": {"ticket_id": "OLD"}, "validated": {"issues": []}, "final_report": "old"}
    loaded = client.post("/api/v1/sessions/load", json={"payload": legacy})
    assert loaded.status_code == 200
    session = loaded.json()["session"]
    assert session["migration"]["strategy"] == "wrapped_without_field_loss"
    assert session["original_legacy_payload"] == legacy


def test_report_download_and_run_history(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "report"}).json()["run_id"]
    wait_terminal(client, run_id)
    report = client.get(f"/api/v1/runs/{run_id}/report/download")
    assert report.status_code == 200
    assert "Fake RCA Report" in report.text
    history = client.get("/api/v1/runs").json()
    assert any(x["run_id"] == run_id for x in history)
    metrics = client.get(f"/api/v1/runs/{run_id}/metrics").json()
    assert metrics["model_calls"][0]["model"] == "fake-model"
    assert "system_start" in metrics and "system_end" in metrics


def test_unsupported_inference_parameter_is_rejected(tmp_path):
    deployment = DeploymentConfig(profile_name="No Flash", type="local", storage_root=str(tmp_path), auth_required=False, cors_origins=[], feature_overrides={"flash_attention": False})
    app, _, _ = make_stack(tmp_path, deployment)
    client = TestClient(app)
    cfg = client.get("/api/v1/config").json()
    cfg["inference"]["flash_attention"] = True
    response = client.put("/api/v1/config", json={"config": cfg})
    assert response.status_code == 422
    assert "flash_attention" in response.text


def test_capability_discovery_and_system_metrics_are_observational(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    caps = client.get("/api/v1/capabilities")
    assert caps.status_code == 200
    assert "features" in caps.json() and "models" in caps.json()
    system = client.get("/api/v1/system")
    assert system.status_code == 200
    assert "ram_total_gb" in system.json()


def test_remote_profile_requires_bearer_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("RCA_API_TOKEN", "secret-token")
    deployment = DeploymentConfig(profile_name="RunPod", type="runpod", storage_root=str(tmp_path), auth_required=True, cors_origins=[])
    app, _, _ = make_stack(tmp_path, deployment)
    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 401
    assert client.get("/api/v1/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/health", headers={"Authorization": "Bearer secret-token"}).status_code == 200


def test_deployment_profile_files_cover_three_targets():
    root = Path(__file__).resolve().parent.parent
    for name, expected in (("local-dell", "local"), ("runpod", "runpod"), ("home-ai-server", "home")):
        settings = BackendSettings.load(root) if False else None
        import yaml
        data = yaml.safe_load((root / "configs" / "deployment" / f"{name}.yaml").read_text(encoding="utf-8"))
        assert data["deployment"]["type"] == expected
        assert data["deployment"]["storage_root"]


def test_rca_core_pipeline_has_no_direct_lmstudio_import():
    root = Path(__file__).resolve().parent.parent
    source = (root / "rca_app" / "pipeline.py").read_text(encoding="utf-8")
    assert "from .lmstudio_client" not in source
    assert "from .model_protocol import ModelClient" in source


def test_sse_event_endpoint_replays_pipeline_events(tmp_path):
    app, _, _ = make_stack(tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/v1/runs", json={"run_type": "single", "raw_case": "event"}).json()["run_id"]
    wait_terminal(client, run_id)
    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as response:
        text = "".join(response.iter_text())
    assert "event: pipeline_stage" in text
    assert "event: terminal" in text


def test_frontend_backend_profile_switching_contract_is_present():
    root = Path(__file__).resolve().parent.parent
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    for token in ("Local Dell", "RunPod Development", "Home AI Server", "Custom endpoint", "rca.backendProfiles", "selectProfile", "backend_url"):
        assert token in js
    assert "/api/v1" in js


def test_desktop_migration_matrix_covers_all_result_views_and_stop():
    root = Path(__file__).resolve().parent.parent
    text = (root / "docs" / "DESKTOP_UI_MIGRATION_MATRIX.md").read_text(encoding="utf-8")
    for token in ("Final Report", "Live Pipeline", "Stage Log", "Sequential Batch", "Validation", "Canonical Input", "Structured JSON", "API Stats", "LLM Attempts", "Repair Routing", "Stop/Abort"):
        assert token in text


def test_release_documentation_set_exists():
    root = Path(__file__).resolve().parent.parent
    required = [
        "README.md", "CHANGELOG.md", "VERSION_HISTORY.md", "docs/ARCHITECTURE.md",
        "docs/V1.8.5_RELEASE_NOTES.md", "docs/API.md", "docs/CONFIGURATION.md",
        "docs/DEPLOY_LOCAL_DELL.md", "docs/DEPLOY_RUNPOD.md", "docs/DEPLOY_HOME_AI_SERVER.md",
        "docs/DESKTOP_UI_MIGRATION_MATRIX.md", "docs/RCA_CORE_ARCHITECTURE_v0.8.4.md",
    ]
    for rel in required:
        assert (root / rel).exists(), rel


def test_backend_app_imports_for_supported_runtime():
    from rca_server.app import create_app
    app = create_app()
    assert app is not None
