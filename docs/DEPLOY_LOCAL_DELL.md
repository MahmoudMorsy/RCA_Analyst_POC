# Local Dell Deployment

## Goal

Run Web UI + RCA backend + RCA core locally, with LM Studio/llama.cpp/OpenAI-compatible inference on the same Dell.

## Setup

1. Extract the release.
2. Run `setup.bat`.
3. Start LM Studio server (typical `http://127.0.0.1:1234/v1`).
4. Run `run.bat`.
5. Open `http://localhost:8000`.
6. Select **Local Dell** in Backend Profiles.
7. Configure primary and small model IDs.
8. Test backend and model connections.

The default backend binds only to `127.0.0.1` and does not require an API token.

## Desktop fallback

`run_desktop.bat` retains the v0.8.4-style PySide interface for parity checks during migration validation.
