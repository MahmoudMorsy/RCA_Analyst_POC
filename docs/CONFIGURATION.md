# v1.8.5 Configuration Reference

## Deployment profile

YAML under `configs/deployment/` controls backend bind/storage/security/capability declarations. Select with `RCA_DEPLOYMENT_PROFILE`.

## Application configuration

Persisted under `<storage_root>/config/application.json`.

Top-level sections:

### `rca`

Preserves v0.8.4 `AppConfig` field names for semantic migration safety, including active and hidden compatibility settings.

### `primary_model`

- `provider`
- `endpoint`
- `model`
- `temperature`
- `reasoning_effort`
- `max_tokens`
- `context_size`
- `timeout_seconds`
- `thinking_mode`
- `transport`
- `api_token_env`

### `small_model`

Same independent fields for the 4B/small-model services.

### `inference`

- `cpu_threads`
- `gpu_layers`
- `gpu_offload`
- `tensor_split`
- `flash_attention`
- `batch_size`
- `eval_batch_size`
- `parallel_slots`
- `context_size_override`
- `provider_options`

Unsupported active parameters are rejected with HTTP 422; the Web UI capability-gates them first.

## Environment overrides

- `RCA_DEPLOYMENT_PROFILE`
- `RCA_STORAGE_ROOT`
- `RCA_API_TOKEN`
- `RCA_CORS_ORIGINS`
- `RCA_MAX_CONCURRENT_RUNS`
- `RCA_PRIMARY_ENDPOINT`
- `RCA_SMALL_ENDPOINT`
- `RCA_PRIMARY_MODEL`
- `RCA_SMALL_MODEL`
- `RCA_PRIMARY_PROVIDER`
- `RCA_SMALL_PROVIDER`
- `LM_API_TOKEN` (default model-server token environment variable)

Environment endpoint/model overrides apply at deployment runtime and do not rewrite RCA core behavior.
