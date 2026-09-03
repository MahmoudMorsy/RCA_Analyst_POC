# Local Dell Deployment — v1.8.10

## Goal

Run the same Web UI + FastAPI backend + RCA Core v0.8.9 locally with LM Studio/llama.cpp/OpenAI-compatible inference.

## Setup

1. Extract the release.
2. Run `setup.bat`.
3. Start the local model server(s).
4. Run `run.bat`.
5. Open `http://localhost:8000`.
6. Select **Local Dell**.
7. Configure/test Primary and Small / Utility model roles.
8. Choose Critical Semantic Model Routing if a stronger model should perform semantic preparation and/or verification.

The default backend binds only to `127.0.0.1` and does not require an API token.

## Python compatibility

The supported Dell runtime remains Python 3.9+. v1.8.10 retains the server-layer compatibility fix introduced in v1.8.5.

## Context and model-server settings

The Web backend does not own LM Studio/llama.cpp process lifecycle. Context size, GPU offload, Flash Attention and similar launch parameters must be configured in the model server itself unless a future provider adapter explicitly exposes runtime control.

The Web form may record/check expected context metadata, but it does not change a model already loaded at another context size.

## Recommended validation

For cross-hardware comparison, keep RCA stage settings and semantic routing equivalent between Dell and RunPod. Quantization differences should be recorded as model metadata rather than treated as identical model execution.

## Desktop fallback

`run_desktop.bat` retains the desktop interface for parity checks. Web mode is the active application architecture.


## v1.8.9 browser reconnect

A page reload/tab restart can reattach to a still-running local backend run. A backend process restart cannot resume an in-flight worker.
