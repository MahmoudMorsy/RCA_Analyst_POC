# RCA Analyst v1.8.12 Configuration Reference

## Top-level application configuration

Persisted under `<storage_root>/config/application.json`.

### `rca`

Retains existing `AppConfig` compatibility fields. The active semantic topology remains controlled by the established v0.8 switches/budgets; old v0.7-compatible fields are retained for deterministic round-trip migration.

### `primary_model` / `small_model`

Each role contains:

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

`context_size` is expected/provider metadata in v1.8.12; discovery may populate it from explicit provider runtime metadata (for example llama.cpp `/props`). It does not reconfigure an already-running external model server.

### `model_routing` — new in v1.8.7

```json
{
  "semantic_preparation_role": "small",
  "semantic_verification_role": "small",
  "semantic_preparation_reasoning_effort": "provider_default",
  "semantic_preparation_thinking_mode": "off",
  "semantic_verification_reasoning_effort": "provider_default",
  "semantic_verification_thinking_mode": "off"
}
```

Allowed roles are `small` and `primary`.

- semantic preparation role owns Requirement IR compilation, structural semantic completion, evidence annotation and targeted evidence completion;
- semantic verification role owns the independent original-requirement vs candidate-IR verifier, including post-arbitration verification;
- changing these fields changes model capacity/transport only. Python retains deterministic compliance authority.


### v1.8.9 semantic-contract note

v1.8.9 does not add testcase-specific tuning controls. Missing Requirement IR recovery, provenance completion, source grounding, materiality and RCA fact-ID validation are core contracts. Critical Semantic Model Routing remains the mechanism for choosing Small / Utility or Primary capacity for semantic preparation and verification.

Keep model/server settings stable across a live regression batch. Changing context, reasoning, routing or token budgets mid-run invalidates performance comparisons and can obscure whether a semantic-core fix worked.

### Qwen/llama.cpp thinking control — v1.8.7

For OpenAI-compatible chat transport, an explicit role `thinking_mode=off` is sent as `chat_template_kwargs.enable_thinking=false`; `on` sends `true`; `provider_default` omits the option. If a compatible provider rejects the optional field with HTTP 400/422, one bounded transport fallback removes only that field.

Telemetry records provider-reported reasoning tokens separately from `reasoning_content_present` / `reasoning_content_chars`, so a provider returning reasoning text despite Thinking Off is visible rather than reported as zero-reasoning activity.

### `inference`

Fields remain preserved:

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

Important v1.8.9 behavior: the FastAPI backend does not currently own external LM Studio/llama.cpp/vLLM process lifecycle. Consequently these controls are capability-disabled unless a deployment adapter explicitly advertises backend ownership. They must not imply that editing the Web form changes `llama-server -c`, GPU layers, Flash Attention, etc.

## Environment overrides

Deployment variables include:

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
- model API-token environment variables such as `LM_API_TOKEN`.

The six model endpoint/model/provider environment variables override file configuration when the backend loads its deployment defaults. v1.8.11 exposes these active overrides in `/capabilities` and the Web UI so a successful save cannot misleadingly appear to disappear without explanation.

A Web-started run additionally supplies the current form through `config_override`. That run snapshot is authoritative for that run and is persisted in `config_snapshot.json`/session metadata.

## Context-size rule

There are three distinct concepts:

1. model training maximum (provider/model metadata);
2. actual server runtime context, e.g. llama.cpp `-c 8192`;
3. RCA configuration metadata/expectation.

Only (2) controls the running server's real context window. v1.8.11 model discovery displays provider-advertised runtime context when available so mismatches are visible.


## v1.8.9 Web state

Active-run rediscovery is backend-driven and requires no new RCA semantic configuration. Browser local state stores only UI preferences/selection hints. Critical semantic routing remains explicit and should be verified from the run/session model-call telemetry.


### Model discovery versus model loading

Discovery is observational. A reachable endpoint with no advertised models is reported as `NO_MODELS`; RCA Analyst does not load the model on behalf of LM Studio/llama.cpp/vLLM. Editing an endpoint invalidates the previous endpoint-specific model/context selection in the Web form until discovery is run again.
