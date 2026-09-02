# Home AI Server Deployment

The home server uses the same application/container as Dell and RunPod.

Primary changes are configuration only:

- deployment profile: `home-ai-server`;
- storage root;
- primary/small model endpoints;
- inference provider;
- authentication/TLS endpoint;
- hardware-specific model-server startup parameters.

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

A dual-3090, single-3090 or future accelerator changes the inference service/profile, not the RCA application code.
