# Home AI Server Deployment — v1.8.13

The home server uses the **same** v1.8.11 application/container as Dell and RunPod. No hardware-specific code fork is allowed.

Configuration differences are limited to:

- deployment profile;
- storage root;
- Primary and Small / Utility endpoints/models;
- Critical Semantic Model Routing;
- authentication/TLS edge;
- provider-specific model-server launch parameters.

Example:

```bash
export RCA_DEPLOYMENT_PROFILE=home-ai-server
export RCA_STORAGE_ROOT=/srv/rca-data
export RCA_API_TOKEN='<strong-token>'
export RCA_CORS_ORIGINS='https://rca.home.example'
export RCA_PRIMARY_ENDPOINT='http://127.0.0.1:8001/v1'
export RCA_SMALL_ENDPOINT='http://127.0.0.1:8002/v1'
python run_web.py
```

A dual-GPU or different accelerator changes inference-server configuration, not RCA semantics.

As on RunPod, v1.8.11 does not own external model-server lifecycle. Set real context/offload/batching in the model server and use the Web UI for discovery, testing, role routing and reproducible per-run snapshots.


## v1.8.9 browser reconnect

The Web client automatically rediscovers non-terminal runs from the server after authentication. Backend process restart semantics are unchanged.


### v1.8.12+ model-server check
Use **Discover at Endpoint** after starting or changing an external model server. An empty loaded-model catalog is now an explicit error state. Use **Test Model** to run a minimal inference probe before starting a long RCA suite; the discovered runtime context is shown when the provider exposes it.
