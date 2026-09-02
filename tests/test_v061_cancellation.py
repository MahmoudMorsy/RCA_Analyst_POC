from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from rca_app.cancellation import AnalysisCancelled, CancellationToken
from rca_app.lmstudio_client import LMStudioClient
from rca_app.pipeline import RCAPipeline


class _TinyResponse(BaseModel):
    value: str


class _FakeStreamResponse:
    def __init__(self, token: CancellationToken):
        self.token = token
        self.closed = False
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_lines(self, chunk_size=1, decode_unicode=True):
        first = {
            "choices": [{"index": 0, "delta": {"content": '{"value":"par'}, "finish_reason": None}]
        }
        yield "data: " + json.dumps(first)
        self.token.cancel("unit-test stop")
        second = {
            "choices": [{"index": 0, "delta": {"content": 'tial"}'}, "finish_reason": "stop"}]
        }
        yield "data: " + json.dumps(second)
        yield "data: [DONE]"

    def close(self):
        self.closed = True


def test_streaming_model_request_aborts_and_rejects_partial_json(monkeypatch):
    token = CancellationToken()
    fake = _FakeStreamResponse(token)

    def fake_post(*args, **kwargs):
        assert kwargs.get("stream") is True
        assert kwargs["json"]["stream"] is True
        assert kwargs["json"]["stream_options"]["include_usage"] is True
        return fake

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    client = LMStudioClient(
        "http://127.0.0.1:1234/v1",
        "fake-model",
        cancellation_token=token,
    )

    with pytest.raises(AnalysisCancelled):
        client.structured_chat("system", "user", _TinyResponse, "tiny")

    assert fake.closed is True


def test_precancelled_pipeline_never_calls_primary_model():
    class NeverCallClient:
        model = "never-call"

        def structured_chat(self, *args, **kwargs):
            raise AssertionError("model must not be called after cancellation")

    token = CancellationToken()
    token.cancel("stop before start")
    pipeline = RCAPipeline(NeverCallClient(), cancellation_token=token)

    with pytest.raises(AnalysisCancelled):
        pipeline.run("[REQUIREMENTS]\nREQ-1: X shall be ON.\n")


def test_gui_source_exposes_stop_button_and_cooperative_cancel_path():
    source = (Path(__file__).resolve().parent.parent / "rca_app" / "gui.py").read_text(encoding="utf-8")
    assert 'self.stop_btn = QPushButton("Stop")' in source
    assert "self._worker.request_cancel()" in source
    assert "CancellationToken()" in source
    assert "worker.cancelled.connect(self._on_cancelled)" in source
    assert "worker.cancelled.connect(self._on_batch_cancelled)" in source

class _SuccessfulStreamResponse:
    def __init__(self, lines):
        self.lines = list(lines)
        self.closed = False
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_lines(self, chunk_size=1, decode_unicode=True):
        yield from self.lines

    def close(self):
        self.closed = True


def test_cancellable_chat_stream_reconstructs_structured_output_and_usage(monkeypatch):
    token = CancellationToken()
    lines = [
        'data: ' + json.dumps({"choices": [{"delta": {"reasoning_content": "check "}, "finish_reason": None}]}),
        'data: ' + json.dumps({"choices": [{"delta": {"content": '{"value":'}, "finish_reason": None}]}),
        'data: ' + json.dumps({"choices": [{"delta": {"content": '"ok"}'}, "finish_reason": "stop"}]}),
        'data: ' + json.dumps({"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8, "completion_tokens_details": {"reasoning_tokens": 1}}}),
        'data: [DONE]',
    ]
    fake = _SuccessfulStreamResponse(lines)
    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", lambda *a, **k: fake)
    client = LMStudioClient("http://127.0.0.1:1234/v1", "fake-model", cancellation_token=token)

    result = client.structured_chat("system", "user", _TinyResponse, "tiny")

    assert result.parsed.value == "ok"
    assert result.reasoning_content == "check "
    assert result.stats.prompt_tokens == 5
    assert result.stats.completion_tokens == 3
    assert result.stats.reasoning_tokens == 1
    assert fake.closed is True


def test_cancellable_manual_qwen_stream_reconstructs_json_and_usage(monkeypatch):
    token = CancellationToken()
    lines = [
        'data: ' + json.dumps({"choices": [{"text": '{"value":', "finish_reason": None}]}),
        'data: ' + json.dumps({"choices": [{"text": '"ok"}', "finish_reason": "stop"}]}),
        'data: ' + json.dumps({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}}),
        'data: [DONE]',
    ]
    fake = _SuccessfulStreamResponse(lines)
    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", lambda *a, **k: fake)
    client = LMStudioClient(
        "http://127.0.0.1:1234/v1",
        "qwen/qwen3.5-4b",
        thinking_mode="off",
        transport="qwen35-manual",
        cancellation_token=token,
    )

    result = client.structured_repair("system", "user", _TinyResponse, "tiny")

    assert result.parsed.value == "ok"
    assert result.stats.prompt_tokens == 7
    assert result.stats.completion_tokens == 4
    assert result.transport == "qwen35-manual"
    assert fake.closed is True
