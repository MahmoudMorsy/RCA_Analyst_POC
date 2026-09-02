# v1.8.4 Migration Risks and Coupling Inventory

## Current UI/business-logic coupling

1. `rca_app.gui._build_pipeline()` constructs every model client and the `RCAPipeline` directly from Qt configuration.
2. `MainWindow.analyze_case()` owns worker-thread lifecycle, run state, cancellation and result promotion.
3. `BatchAnalysisWorker` owns sequential batch execution and output persistence.
4. Qt callbacks own live pipeline state and stage history in memory.
5. Report/session export writes directly to arbitrary local filesystem paths.
6. Saved config lives under `~/.rca_analyst_poc/config.json` and mixes RCA behavior, model endpoint/provider details and UI theme.
7. CLI duplicates model-client/pipeline construction logic.

## Model-provider dependencies

- `RCAPipeline` is typed directly against `LMStudioClient` and catches `LMStudioError`.
- The pipeline creates an LM-Studio-specific fallback client for final wording review.
- GUI and CLI directly use LM Studio `/models` and completion endpoints.
- Base URL is effectively both deployment/provider configuration and model endpoint.

Migration: introduce provider-neutral `ModelClient` protocol + `ModelGateway`; keep `LMStudioClient` only as a compatibility/OpenAI-compatible transport implementation.

## Filesystem/path assumptions

- `AppConfig`: user-home fixed path `~/.rca_analyst_poc/config.json`.
- examples: package-relative local files.
- batch results: package-relative `batch_results/<timestamp>`.
- desktop exports: browser-equivalent functionality does not exist; Qt uses arbitrary local save dialogs.
- test bundle: Qt reads ZIP directly from local machine.

Migration: backend `StorageBackend` with configurable root; all browser file interaction through API.

## Session/schema dependencies

The desktop session is effectively raw `PipelineResult.model_dump()` or a failed-session diagnostic dictionary. There is no explicit envelope/schema version. v1.8.4 adds a versioned envelope while retaining the original legacy payload verbatim during migration.

## Migration risks

1. **Semantic regression through refactor** — mitigated by leaving RCA core modules intact and running the complete existing regression suite.
2. **Cancellation behavior changes** — backend must retain one `CancellationToken`/active model client per run and persist CANCELLED state.
3. **Browser disconnect** — job execution cannot be tied to request lifetime; use backend worker thread/job manager.
4. **Concurrent config mutation** — snapshot configuration at run creation; a running job never reads mutable global UI state.
5. **Run restart/recovery** — persisted run metadata is authoritative; browser reload reconstructs state. Process-restart resume is not promised in v1.8.4, but incomplete jobs are preserved and marked interrupted rather than lost.
6. **Provider-specific engine settings** — capability gate them; never leak provider behavior into RCA core.
7. **Remote security** — bearer auth when enabled, explicit CORS, model ports remain private.
8. **Telemetry absence** — telemetry is best-effort and never blocks RCA.

## Non-blocking ambiguity resolutions

- Web technology: dependency-light static SPA (HTML/CSS/ES modules) served by the FastAPI backend. This avoids a Node build/runtime dependency while still providing a modern live UI. The frontend remains physically separated under `web/` and can later be hosted independently.
- Job persistence: modular-monolith in-process worker threads + filesystem run journal. This satisfies browser disconnect/reconnect without introducing Celery/Redis for the current POC.
- Database: not introduced. JSON/files remain authoritative behind a storage abstraction.
