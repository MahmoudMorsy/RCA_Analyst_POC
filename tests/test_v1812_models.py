from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rca_app.lmstudio_client import LMStudioClient
from rca_server.app import create_app
from rca_server.backend_config import BackendSettings, ConfigStore, DeploymentConfig, ModelRoleConfig
from rca_server.run_manager import RunManager
from rca_server.storage import LocalStorageBackend


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


def _app(tmp_path):
    deployment = DeploymentConfig(
        profile_name="Model Test",
        type="local",
        storage_root=str(tmp_path),
        auth_required=False,
        cors_origins=[],
    )
    settings = BackendSettings(deployment, tmp_path / "config" / "application.json")
    storage = LocalStorageBackend(tmp_path)
    store = ConfigStore(tmp_path / "config" / "application.json")
    manager = RunManager(storage, settings, store, max_workers=1)
    return create_app(settings=settings, run_manager=manager)


def test_v1812_model_catalog_accepts_models_name_alias_and_discovers_llamacpp_runtime_context(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/v1/models"):
            return _Response({"models": [{"name": "/workspace/models/qwen.gguf", "meta": {}}]})
        if url.endswith("/props"):
            return _Response({"default_generation_settings": {"n_ctx": 16384}})
        return _Response({}, 404)

    monkeypatch.setattr("rca_app.lmstudio_client.requests.get", fake_get)
    client = LMStudioClient(base_url="http://127.0.0.1:8003/v1", model="")
    catalog = client.model_catalog()
    assert catalog[0]["id"] == "/workspace/models/qwen.gguf"
    assert catalog[0]["meta"]["runtime_context_size"] == 16384
    assert "http://127.0.0.1:8003/props" in calls


def test_v1812_discover_empty_catalog_is_explicit_error_state(tmp_path, monkeypatch):
    monkeypatch.setattr("rca_server.app.ModelGateway.model_catalog", lambda self, spec: [])
    client = TestClient(_app(tmp_path))
    role_cfg = ModelRoleConfig(endpoint="http://127.0.0.1:8004/v1", model="stale").model_dump(mode="json")
    data = client.post("/api/v1/models/discover", json={"role": "small", "config": role_cfg}).json()
    assert data["status"] == "NO_MODELS"
    assert data["resolved_model"] == ""
    assert data["models"] == []
    assert "no loaded models" in data["error"].lower()


def test_v1812_discover_resolves_single_model_and_runtime_context(tmp_path, monkeypatch):
    def fake_catalog(self, spec):
        return [{"id": "new-endpoint-model", "meta": {"runtime_context_size": 32768}}]

    monkeypatch.setattr("rca_server.app.ModelGateway.model_catalog", fake_catalog)
    client = TestClient(_app(tmp_path))
    role_cfg = ModelRoleConfig(endpoint="http://new:9000/v1", model="old-endpoint-model").model_dump(mode="json")
    data = client.post("/api/v1/models/discover", json={"role": "primary", "config": role_cfg}).json()
    assert data["status"] == "AVAILABLE"
    assert data["resolved_model"] == "new-endpoint-model"
    assert data["context_size"] == 32768


def test_v1812_model_test_rejects_reachable_endpoint_with_no_loaded_model(monkeypatch):
    client = LMStudioClient(base_url="http://127.0.0.1:8004/v1", model="")
    monkeypatch.setattr(client, "model_catalog", lambda: [])
    ok, message = client.test_connection()
    assert ok is False
    assert "no loaded model" in message.lower()


def test_v1812_model_test_executes_lightweight_inference_probe(monkeypatch):
    posted = []
    client = LMStudioClient(base_url="http://127.0.0.1:8003/v1", model="qwen", thinking_mode="off")
    monkeypatch.setattr(client, "model_catalog", lambda: [{"id": "qwen", "meta": {"n_ctx": 8192}}])

    def fake_post(url, **kwargs):
        posted.append((url, kwargs.get("json")))
        return _Response({"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    ok, message = client.test_connection()
    assert ok is True
    assert posted[0][0].endswith("/v1/chat/completions")
    assert posted[0][1]["model"] == "qwen"
    assert posted[0][1]["max_tokens"] == 1
    assert posted[0][1]["chat_template_kwargs"]["enable_thinking"] is False
    assert "Context: 8192" in message


def test_v1812_frontend_invalidates_endpoint_and_shows_persistent_discovery_test_status():
    root = Path(__file__).resolve().parent.parent
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "app.js").read_text(encoding="utf-8")
    for token in ("primaryModelStatus", "smallModelStatus"):
        assert token in html
    for token in (
        "invalidateModelEndpoint",
        "Endpoint changed — click Discover at Endpoint.",
        "resolved_model",
        "context_size",
        "Testing…",
        "Discovering…",
    ):
        assert token in js


def test_v1812_model_test_uses_configured_manual_completion_transport(monkeypatch):
    posted = []
    client = LMStudioClient(
        base_url="http://127.0.0.1:8004/v1",
        model="qwen3.5-4b",
        thinking_mode="off",
        transport="qwen35-manual",
    )
    monkeypatch.setattr(client, "model_catalog", lambda: [{"id": "qwen3.5-4b"}])

    def fake_post(url, **kwargs):
        posted.append((url, kwargs.get("json")))
        return _Response({"choices": [{"text": "OK", "finish_reason": "stop"}]})

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    ok, message = client.test_connection()
    assert ok is True
    assert posted[0][0].endswith("/v1/completions")
    assert posted[0][1]["prompt"] == "Reply with OK."
    assert "qwen35-manual" in message
