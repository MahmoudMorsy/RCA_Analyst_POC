# v1.8.4 Target Module Architecture

```text
RCA_Analyst_POC/
├─ rca_app/                       # frozen RCA domain/core + legacy desktop fallback
│  ├─ pipeline.py
│  ├─ validator.py
│  ├─ compliance_engine.py
│  ├─ semantic_*.py
│  ├─ model_protocol.py           # provider-neutral core contract
│  ├─ model_gateway.py            # provider/client factory
│  ├─ lmstudio_client.py          # OpenAI-compatible legacy transport implementation
│  └─ gui.py                      # frozen desktop fallback/reference
├─ rca_server/                    # modular-monolith backend
│  ├─ app.py                      # FastAPI application factory
│  ├─ api_models.py               # API-only Pydantic schemas
│  ├─ auth.py
│  ├─ backend_config.py           # RCA / inference / infrastructure separation
│  ├─ deployment.py
│  ├─ pipeline_factory.py
│  ├─ run_manager.py
│  ├─ storage.py
│  ├─ sessions.py
│  ├─ system_info.py
│  └─ telemetry.py
├─ web/                           # zero-RCA-logic browser frontend
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
├─ configs/deployment/
│  ├─ local-dell.yaml
│  ├─ runpod.yaml
│  └─ home-ai-server.yaml
├─ docs/
│  ├─ ARCHITECTURE.md
│  ├─ DESKTOP_UI_MIGRATION_MATRIX.md
│  ├─ API.md
│  ├─ CONFIGURATION.md
│  ├─ DEPLOY_LOCAL_DELL.md
│  ├─ DEPLOY_RUNPOD.md
│  └─ DEPLOY_HOME_AI_SERVER.md
├─ Dockerfile
├─ docker-compose.yml
├─ run_web.py
└─ run_desktop.py                # explicit frozen desktop fallback
```

The browser never imports or reimplements `rca_app` logic. `rca_server.pipeline_factory` is the only deployment layer allowed to translate API/configuration into model clients and an `RCAPipeline` instance.
