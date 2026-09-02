# RunPod Deployment Guide

## Persistent layout

Use persistent `/workspace` storage for code, models and RCA data. The included RunPod profile defaults RCA data to `/workspace/rca-data`.

Recommended:

```text
/workspace/rca/        Git checkout/worktree
/workspace/rca-data/   sessions/runs/uploads/config
/workspace/models/     model cache/files
```

## Environment

```bash
export RCA_DEPLOYMENT_PROFILE=runpod
export RCA_STORAGE_ROOT=/workspace/rca-data
export RCA_API_TOKEN='<strong-random-token>'
export RCA_CORS_ORIGINS='https://<your-ui-origin>'
export RCA_PRIMARY_ENDPOINT='http://127.0.0.1:<primary-port>/v1'
export RCA_SMALL_ENDPOINT='http://127.0.0.1:<small-port>/v1'
export RCA_PRIMARY_PROVIDER=vllm
export RCA_SMALL_PROVIDER=vllm
```

Set model IDs with environment variables or Web configuration.

## Start

```bash
python -m pip install -r requirements.txt
python run_web.py
```

or build the Docker image.

## Security/networking

Expose only the RCA Web/API endpoint through RunPod's HTTPS proxy or another TLS endpoint. Keep vLLM/LM Studio/llama.cpp ports internal to the pod wherever possible.

## Development workflow

- keep the Git checkout on persistent storage;
- use SSH / VS Code Remote SSH for development;
- keep model files/cache under persistent `/workspace`;
- stopping the GPU pod must not remove `/workspace/rca-data`;
- browser disconnection does not stop active RCA runs; the backend continues and persists state.
