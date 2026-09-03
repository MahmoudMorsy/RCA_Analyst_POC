# RunPod Deployment Guide — v1.8.9

## Persistent layout

Use persistent `/workspace` storage:

```text
/workspace/rca/        RCA package/worktree
/workspace/rca-data/   sessions/runs/uploads/config
/workspace/models/     GGUF/model files
```

## Environment

Example:

```bash
export RCA_DEPLOYMENT_PROFILE=runpod
export RCA_STORAGE_ROOT=/workspace/rca-data
export RCA_API_TOKEN='<strong-random-token>'
export RCA_CORS_ORIGINS='https://<your-ui-origin>'
export RCA_PRIMARY_ENDPOINT='http://127.0.0.1:8003/v1'
export RCA_SMALL_ENDPOINT='http://127.0.0.1:8004/v1'
export RCA_PRIMARY_PROVIDER='openai-compatible'
export RCA_SMALL_PROVIDER='openai-compatible'
```

Model IDs may be provided by environment defaults or current Web form/run configuration.

## Model-server launch parameters

v1.8.9 does **not** start or reconfigure external llama.cpp/vLLM/LM Studio processes. Context must therefore be set when each model server is launched.

Example llama.cpp pattern:

```bash
llama-server \
  -m /workspace/models/<model>.gguf \
  --host 127.0.0.1 \
  --port 8004 \
  -ngl 999 \
  -c 32768 \
  --flash-attn on
```

Do not infer actual context from a Web field. Confirm the live server:

```bash
curl http://127.0.0.1:8004/v1/models
```

For llama.cpp, inspect returned `n_ctx`.

## Critical Semantic Model Routing

v1.8.9 can route critical semantic work without killing servers or patching code:

- Semantic Preparation → Small / Utility or Primary
- Semantic Verification → Small / Utility or Primary

This allows configurations such as:

```text
Utility intake/review      -> Qwen3.5-4B
Semantic Preparation      -> Qwen3.8-27B
Semantic Verification     -> Qwen3.8-27B
Semantic Arbitration/RCA  -> Primary 27B
```

Python remains authoritative for compliance regardless of the selected model capacity.

## Environment override behavior

`RCA_PRIMARY_*` / `RCA_SMALL_*` variables are deployment defaults and are shown explicitly in the Web UI when active. A run carries its own configuration snapshot so one-off model-routing experiments do not require changing source code.

## Start backend

```bash
python -m pip install -r requirements.txt
python run_web.py
```

or use the included container files.

## Security/networking

Expose only the RCA Web/API endpoint through RunPod HTTPS proxy/reverse proxy where practical. Keep model ports internal (`127.0.0.1`).

## Operational diagnostics

Useful checks:

```bash
ss -ltnp | grep -E '8000|8003|8004'
ps -ef | grep -E 'llama-server|vllm' | grep -v grep
curl -sS http://127.0.0.1:8003/v1/models
curl -sS http://127.0.0.1:8004/v1/models
nvidia-smi
```

A model name shown in a pipeline stage proves selected configuration, not necessarily successful inference. Endpoint/model/transport are now exposed in stage/model-call telemetry to make that boundary visible.

## Validation sequence

After deployment:

1. test backend health;
2. discover/test both model endpoints;
3. run TC17 first;
4. inspect semantic IR, verifier and deterministic verdicts;
5. run TC12 only after context/output budgets are confirmed;
6. compare semantic acceptance separately from execution status;
7. export the full run bundle for any failure.

## Qwen thinking verification — v1.8.7

When a critical role uses Thinking Off, v1.8.7 sends `chat_template_kwargs.enable_thinking=false` on OpenAI-compatible chat requests. Use the run model-call statistics to confirm `thinking_requested=off` and inspect `reasoning_content_present` / `reasoning_content_chars`. A zero provider reasoning-token count alone no longer proves that no reasoning text was generated.

For the next live acceptance run, route semantic preparation and independent verification to the Primary 27B, keep Thinking Off, run TC17 first, and only proceed to TC12 after TC17 meets the documented semantic target.

## v1.8.9 live full-suite validation

Deploy the exact release ZIP and keep model-server context/routing/reasoning settings stable for the complete batch. Export the full run bundle after completion. Semantic acceptance must be assessed independently from transport execution status.

Watch especially for: missing-ID recovery activity, structural completion counts, semantic arbitration frequency/retries, final semantic-integrity ERROR count, hypothesis provenance acceptance and per-stage token/runtime statistics. TC17 and TC12 remain explicit anchors inside the full-suite rerun. RCA Core v0.8.8 stays candidate until live acceptance succeeds.


## v1.8.9 reconnect note

If the browser tab is closed while a run continues, reconnect/authenticate to the same backend. The Web client will rediscover the active run from `/runs` and resume live polling. Restarting the backend process is different: the lost worker cannot be resumed and partial artifacts remain preserved as an interrupted run.
