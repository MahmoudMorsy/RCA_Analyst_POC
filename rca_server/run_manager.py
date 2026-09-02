from __future__ import annotations

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from rca_app import __version__
from rca_app.cancellation import AnalysisCancelled, CancellationToken
from rca_app.pipeline import PipelineValidationError
from rca_app.test_bundle import (
    builtin_regression_expectations,
    evaluate_semantic_acceptance,
    load_expected_results_manifest,
    load_test_bundle_zip,
)

from .api_models import PipelineStage, RunCreateRequest, RunState, RunSummary
from .backend_config import ApplicationConfig, BackendSettings, ConfigStore
from .pipeline_factory import PipelineFactory
from .sessions import SessionService
from .storage import LocalStorageBackend
from .system_info import SystemInfoService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start: Optional[str], end: Optional[str]) -> Optional[float]:
    if not start or not end:
        return None
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
        return round((b - a).total_seconds() * 1000.0, 3)
    except Exception:
        return None


TERMINAL = {RunState.CANCELLED, RunState.COMPLETED, RunState.FAILED}


@dataclass
class RuntimeRun:
    summary: RunSummary
    request: RunCreateRequest
    config: ApplicationConfig
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    pipeline: Any = None
    stages: dict[str, PipelineStage] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    failure: Optional[dict[str, Any]] = None
    lock: threading.RLock = field(default_factory=threading.RLock)


class RunManager:
    def __init__(
        self,
        storage: LocalStorageBackend,
        settings: BackendSettings,
        config_store: ConfigStore,
        pipeline_factory: Optional[PipelineFactory] = None,
        system_info: Optional[SystemInfoService] = None,
        max_workers: int = 1,
    ):
        self.storage = storage
        self.settings = settings
        self.config_store = config_store
        self.pipeline_factory = pipeline_factory or PipelineFactory()
        self.system_info = system_info or SystemInfoService()
        self.sessions = SessionService(storage)
        self.executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="rca-run")
        self._runs: dict[str, RuntimeRun] = {}
        self._lock = threading.RLock()
        self._load_existing_metadata()

    def _load_existing_metadata(self) -> None:
        for path in (self.storage.root / "runs").glob("*/metadata.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                state = RunState(data.get("status", "FAILED"))
                if state not in TERMINAL:
                    data["status"] = RunState.FAILED.value
                    data["error"] = "Backend process restarted before this run completed. Partial artifacts were preserved."
                    data["finished_at"] = _now()
                    self.storage.write_json(f"runs/{path.parent.name}/metadata.json", data)
            except Exception:
                continue

    def create(self, request: RunCreateRequest) -> RunSummary:
        if request.run_type == "single" and not request.raw_case.strip():
            raise ValueError("raw_case is required for single-case runs")
        if request.run_type == "bundle" and not request.file_id.strip():
            raise ValueError("file_id is required for bundle runs")
        run_id = self._new_run_id(request)
        summary = RunSummary(
            run_id=run_id,
            run_type=request.run_type,
            label=request.label or request.run_type,
            status=RunState.QUEUED,
            created_at=_now(),
        )
        config = copy.deepcopy(request.config_override or self.config_store.load())
        runtime = RuntimeRun(summary=summary, request=request, config=config)
        runtime.metrics = {
            "backend_version": __version__,
            "deployment": self.settings.deployment.model_dump(mode="json"),
            "config_snapshot": config.model_dump(mode="json"),
            "system_start": self.system_info.snapshot(self.storage.root),
            "model_calls": [],
            "pipeline": {},
        }
        with self._lock:
            self._runs[run_id] = runtime
        self._persist(runtime)
        self._event(runtime, "run_state", {"status": RunState.QUEUED.value})
        response = summary.model_copy(deep=True)
        self.executor.submit(self._execute, run_id)
        return response

    def _new_run_id(self, request: RunCreateRequest) -> str:
        stem = "RCA"
        if request.raw_case:
            for line in request.raw_case.splitlines():
                if line.strip().lower().startswith("ticket id:"):
                    stem = line.split(":", 1)[1].strip() or stem
                    break
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{stem}_{stamp}_{uuid4().hex[:6]}".replace(" ", "_")

    def _execute(self, run_id: str) -> None:
        runtime = self._require_runtime(run_id)
        if runtime.cancellation.cancelled:
            self._finish_cancelled(runtime, "Cancelled while queued.")
            return
        self._set_state(runtime, RunState.INITIALIZING)
        runtime.summary.started_at = _now()
        self._persist(runtime)
        try:
            self._set_state(runtime, RunState.RUNNING)
            if runtime.request.run_type == "single":
                self._execute_single(runtime, runtime.request.raw_case)
            elif runtime.request.run_type == "builtin_regression":
                self._execute_builtin(runtime)
            elif runtime.request.run_type == "bundle":
                self._execute_bundle(runtime)
            else:
                raise ValueError(f"Unsupported run_type: {runtime.request.run_type}")
            if runtime.cancellation.cancelled:
                self._finish_cancelled(runtime, runtime.cancellation.reason or "Cancelled by user.")
                return
            self._set_state(runtime, RunState.COMPLETED)
            runtime.summary.finished_at = _now()
            self._finalize_metrics(runtime)
            self._persist(runtime)
            self._auto_session(runtime)
        except AnalysisCancelled as exc:
            self._finish_cancelled(runtime, str(exc))
        except PipelineValidationError as exc:
            runtime.failure = self._failure_payload(str(exc), exc.validated, exc.canonical_case, exc.attempts, exc.stats, exc.repair_log)
            self.storage.write_json(f"runs/{run_id}/failure.json", runtime.failure)
            self._set_failed(runtime, str(exc))
        except Exception as exc:
            runtime.failure = {"status": "FAILED", "message": str(exc)}
            self.storage.write_json(f"runs/{run_id}/failure.json", runtime.failure)
            self._set_failed(runtime, str(exc))

    def _execute_single(self, runtime: RuntimeRun, raw_case: str) -> None:
        pipeline = self.pipeline_factory.build(runtime.config, runtime.cancellation)
        runtime.pipeline = pipeline
        result = pipeline.run(
            raw_case,
            progress=lambda stage, detail: self._progress(runtime, stage, detail),
            trace=lambda event: self._trace(runtime, event),
        )
        runtime.pipeline = None
        payload = result.model_dump(mode="json")
        runtime.result = payload
        self.storage.write_json(f"runs/{runtime.summary.run_id}/result.json", payload)
        self.storage.write_text(f"runs/{runtime.summary.run_id}/report.md", result.final_report)
        self._capture_model_metrics(runtime, payload)

    def _execute_builtin(self, runtime: RuntimeRun) -> None:
        root = Path(__file__).resolve().parent.parent
        cases = []
        for case_id in ("TEST-001", "TEST-002", "TEST-003"):
            path = root / "examples" / f"{case_id}.txt"
            cases.append((case_id, path.read_text(encoding="utf-8")))
        self._execute_case_sequence(runtime, cases, builtin_regression_expectations())

    def _execute_bundle(self, runtime: RuntimeRun) -> None:
        path, _meta = self.storage.get_upload(runtime.request.file_id)
        cases = [(x.case_id, x.raw_text) for x in load_test_bundle_zip(path)]
        expectations = load_expected_results_manifest(path)
        self._execute_case_sequence(runtime, cases, expectations)

    def _execute_case_sequence(self, runtime: RuntimeRun, cases: list[tuple[str, str]], expectations: dict[str, Any]) -> None:
        records = []
        total = len(cases)
        runtime.result = {"run_type": runtime.request.run_type, "cases": records, "count": 0, "total_cases": total}
        self.storage.write_json(f"runs/{runtime.summary.run_id}/result.json", runtime.result)
        for index, (case_id, raw) in enumerate(cases, start=1):
            runtime.cancellation.throw_if_cancelled(f"before batch case {case_id}")
            case_started = time.perf_counter()
            self._progress(runtime, "Sequential Batch", f"[{index}/{total}] {case_id}: STARTED")
            pipeline = self.pipeline_factory.build(runtime.config, runtime.cancellation)
            runtime.pipeline = pipeline
            try:
                result = pipeline.run(
                    raw,
                    progress=lambda s, d, cid=case_id: self._progress(runtime, f"{cid} / {s}", d),
                    trace=lambda event, cid=case_id: self._trace(runtime, {**event, "stage_id": f"{cid}:{event.get('stage_id','stage')}", "title": f"{cid} / {event.get('title','Stage')}"}),
                )
                payload = result.model_dump(mode="json")
                case_dir = f"runs/{runtime.summary.run_id}/cases/{case_id}"
                self.storage.write_json(f"{case_dir}/session.json", payload)
                self.storage.write_text(f"{case_dir}/report.md", result.final_report)
                expected = expectations.get(case_id)
                acceptance = evaluate_semantic_acceptance(result, expected) if expected else None
                self._capture_model_metrics(runtime, payload, case_id=case_id)
                record = {
                    "case_id": case_id,
                    "execution_status": "PASS",
                    "semantic_acceptance": acceptance.model_dump(mode="json") if hasattr(acceptance, "model_dump") else acceptance,
                    "result": payload,
                }
            except PipelineValidationError as exc:
                failure = self._failure_payload(str(exc), exc.validated, exc.canonical_case, exc.attempts, exc.stats, exc.repair_log)
                self.storage.write_json(f"runs/{runtime.summary.run_id}/cases/{case_id}/failure.json", failure)
                self._capture_model_metrics(runtime, failure, case_id=case_id)
                record = {"case_id": case_id, "execution_status": "FAILED", "semantic_acceptance": "NOT_EVALUATED", "failure": failure}
            finally:
                runtime.pipeline = None
            record["statistics"] = self._case_statistics(runtime, case_id, round(time.perf_counter() - case_started, 6), record)
            records.append(record)
            runtime.result = {"run_type": runtime.request.run_type, "cases": records, "count": len(records), "total_cases": total}
            self.storage.write_json(f"runs/{runtime.summary.run_id}/result.json", runtime.result)
            self._progress(runtime, "Sequential Batch", f"[{index}/{total}] {case_id}: {record['execution_status']}")

    def _case_statistics(self, runtime: RuntimeRun, case_id: str, elapsed_seconds: float, record: dict[str, Any]) -> dict[str, Any]:
        calls = [x for x in runtime.metrics.get("model_calls", []) if x.get("case_id") == case_id]
        prompt = sum(int(x.get("prompt_tokens") or 0) for x in calls)
        completion = sum(int(x.get("completion_tokens") or 0) for x in calls)
        reasoning = sum(int(x.get("reasoning_tokens") or 0) for x in calls)
        reasoning_chars = sum(int(x.get("reasoning_content_chars") or 0) for x in calls)
        reasoning_content_calls = sum(1 for x in calls if x.get("reasoning_content_present"))
        model_seconds = sum(float(x.get("request_duration_seconds") or 0.0) for x in calls)
        by_model_role: dict[str, dict[str, Any]] = {}
        for call in calls:
            key = call.get("model_role") or "UNSPECIFIED"
            row = by_model_role.setdefault(key, {"calls": 0, "seconds": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "reasoning_content_chars": 0, "reasoning_content_calls": 0})
            row["calls"] += 1
            row["seconds"] += float(call.get("request_duration_seconds") or 0.0)
            row["prompt_tokens"] += int(call.get("prompt_tokens") or 0)
            row["completion_tokens"] += int(call.get("completion_tokens") or 0)
            row["reasoning_tokens"] += int(call.get("reasoning_tokens") or 0)
            row["reasoning_content_chars"] += int(call.get("reasoning_content_chars") or 0)
            row["reasoning_content_calls"] += 1 if call.get("reasoning_content_present") else 0
        req_counts: dict[str, int] = {}
        payload = record.get("result") or {}
        for row in ((payload.get("validated") or {}).get("requirement_results") or []):
            status = str(row.get("evaluation_status") or "UNKNOWN")
            req_counts[status] = req_counts.get(status, 0) + 1
        return {
            "elapsed_seconds": elapsed_seconds,
            "model_seconds": round(model_seconds, 6),
            "python_seconds_estimate": round(max(elapsed_seconds - model_seconds, 0.0), 6),
            "model_calls": len(calls),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
            "reasoning_content_chars": reasoning_chars,
            "reasoning_content_calls": reasoning_content_calls,
            "total_tokens": prompt + completion,
            "weighted_generation_tokens_per_second": round(completion / model_seconds, 3) if model_seconds > 0 else None,
            "retries": sum(int(x.get("retries") or 0) for x in calls),
            "by_model_role": by_model_role,
            "requirement_result_counts": req_counts,
        }

    @staticmethod
    def _failure_payload(message, validated, canonical, attempts, stats, repair_log):
        def dump(value):
            if value is None: return None
            if isinstance(value, list): return [dump(x) for x in value]
            if hasattr(value, "model_dump"): return value.model_dump(mode="json")
            return value
        return {
            "status": "FAILED",
            "message": message,
            "canonical_case": dump(canonical),
            "validated": dump(validated),
            "attempts": dump(attempts) or [],
            "stats": dump(stats) or [],
            "repair_log": dump(repair_log) or [],
        }

    def cancel(self, run_id: str) -> RunSummary:
        runtime = self._require_runtime(run_id)
        with runtime.lock:
            if runtime.summary.status in TERMINAL:
                return runtime.summary.model_copy(deep=True)
            runtime.summary.status = RunState.CANCELLING
            runtime.cancellation.cancel("Stopped by user through RCA Backend API.")
            if runtime.pipeline is not None:
                runtime.pipeline.cancel("Stopped by user through RCA Backend API.")
            self._event(runtime, "run_state", {"status": RunState.CANCELLING.value})
            self._persist(runtime)
            return runtime.summary.model_copy(deep=True)

    def _finish_cancelled(self, runtime: RuntimeRun, message: str) -> None:
        runtime.summary.status = RunState.CANCELLED
        runtime.summary.error = message
        runtime.summary.finished_at = _now()
        self._log(runtime, "CANCELLED", message)
        self._event(runtime, "run_state", {"status": RunState.CANCELLED.value, "message": message})
        self._finalize_metrics(runtime)
        self._persist(runtime)
        self._auto_session(runtime)

    def _set_failed(self, runtime: RuntimeRun, message: str) -> None:
        runtime.summary.status = RunState.FAILED
        runtime.summary.error = message
        runtime.summary.finished_at = _now()
        self._log(runtime, "FAILED", message)
        self._event(runtime, "run_state", {"status": RunState.FAILED.value, "message": message})
        self._finalize_metrics(runtime)
        self._persist(runtime)
        self._auto_session(runtime)

    def _set_state(self, runtime: RuntimeRun, state: RunState) -> None:
        with runtime.lock:
            runtime.summary.status = state
            self._event(runtime, "run_state", {"status": state.value})
            self._persist(runtime)

    def _progress(self, runtime: RuntimeRun, stage: str, detail: str) -> None:
        with runtime.lock:
            runtime.summary.current_stage = stage
            runtime.summary.progress_detail = detail
            self._log(runtime, stage, detail)
            self._event(runtime, "progress", {"stage": stage, "detail": detail})
            self._persist(runtime)

    def _trace(self, runtime: RuntimeRun, event: dict[str, Any]) -> None:
        with runtime.lock:
            stage_id = str(event.get("stage_id") or f"stage_{len(runtime.stages)+1}")
            now = _now()
            previous = runtime.stages.get(stage_id)
            status = str(event.get("status") or "unknown").upper()
            start = previous.start_time if previous else None
            if status == "RUNNING" and not start:
                start = now
            if status != "RUNNING" and not start:
                start = now
            end = now if status in {"COMPLETE", "FAILED", "SKIPPED", "ATTENTION", "CANCELLED"} else None
            new_metadata = {k: v for k, v in event.items() if k not in {"stage_id", "title", "status", "summary", "input_text", "output_text", "input_data", "output_data"}}
            merged_metadata = dict(previous.metadata) if previous else {}
            merged_metadata.update(new_metadata)
            input_text = str(event.get("input_text") or "") or (previous.input_text if previous else "")
            output_text = str(event.get("output_text") or "") or (previous.output_text if previous else "")
            input_data = event.get("input_data") if event.get("input_data") is not None else (previous.input_data if previous else None)
            output_data = event.get("output_data") if event.get("output_data") is not None else (previous.output_data if previous else None)
            stage = PipelineStage(
                stage_id=stage_id,
                name=str(event.get("title") or (previous.name if previous else stage_id)),
                status=status,
                summary=str(event.get("summary") or (previous.summary if previous else "")),
                start_time=start,
                end_time=end,
                elapsed_ms=_elapsed_ms(start, end),
                input_text=input_text,
                output_text=output_text,
                input_data=input_data,
                output_data=output_data,
                metadata=merged_metadata,
            )
            runtime.stages[stage_id] = stage
            self._event(runtime, "pipeline_stage", stage.model_dump(mode="json"))
            self._persist(runtime)

    def _log(self, runtime: RuntimeRun, stage: str, message: str) -> None:
        item = {"time": _now(), "stage": stage, "message": message}
        runtime.logs.append(item)
        path = self.storage.path(f"runs/{runtime.summary.run_id}/logs.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _event(self, runtime: RuntimeRun, event_type: str, data: dict[str, Any]) -> None:
        event = {"id": len(runtime.events) + 1, "time": _now(), "type": event_type, "data": data}
        runtime.events.append(event)
        path = self.storage.path(f"runs/{runtime.summary.run_id}/events.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _capture_model_metrics(self, runtime: RuntimeRun, payload: dict[str, Any], *, case_id: str = "") -> None:
        stats = payload.get("stats") or []
        attempts = payload.get("attempts") or []
        by_call = {x.get("call_index"): x for x in attempts if isinstance(x, dict)}
        for idx, stat in enumerate(stats, 1):
            elapsed = float(stat.get("elapsed_seconds") or 0)
            completion = int(stat.get("completion_tokens") or 0)
            attempt = by_call.get(idx, {})
            attempt_stage = attempt.get("stage", "")
            endpoint = stat.get("endpoint", "")
            provider = runtime.config.primary_model.provider if endpoint.rstrip("/") == runtime.config.primary_model.endpoint.rstrip("/") else runtime.config.small_model.provider
            stage_id = self._metric_stage_id(case_id, attempt_stage)
            runtime.metrics["model_calls"].append({
                "case_id": case_id,
                "call_index": idx,
                "stage": attempt_stage,
                "stage_id": stage_id,
                "model_role": attempt.get("model_role", ""),
                "model": stat.get("model", ""),
                "endpoint": endpoint,
                "provider": provider,
                "prompt_tokens": int(stat.get("prompt_tokens") or 0),
                "completion_tokens": completion,
                "reasoning_tokens": int(stat.get("reasoning_tokens") or 0),
                "reasoning_content_present": bool(stat.get("reasoning_content_present")),
                "reasoning_content_chars": int(stat.get("reasoning_content_chars") or 0),
                "thinking_requested": str(stat.get("thinking_requested") or "provider_default"),
                "total_tokens": int(stat.get("total_tokens") or 0),
                "request_duration_seconds": elapsed,
                "generation_tokens_per_second": round(completion / elapsed, 3) if elapsed > 0 else None,
                "prompt_processing_tokens_per_second": None,
                "time_to_first_token_seconds": None,
                "model_load_time_seconds": None,
                "finish_reason": attempt.get("finish_reason", ""),
                "retries": int(stat.get("retries") or 0),
                "transport": attempt.get("transport", ""),
            })
        # Keep per-stage metrics useful during active/reconnectable runs, not only
        # after terminal finalization.  This is observational and never affects RCA logic.
        self._attach_stage_statistics(runtime)
        self._persist(runtime)

    @staticmethod
    def _metric_stage_id(case_id: str, attempt_stage: str) -> str:
        stage = attempt_stage or ""
        if stage.startswith("semantic_preparation_requirements_"):
            try:
                n = int(stage.rsplit("_", 1)[1])
                base = f"06_req_{n:02d}"
            except Exception:
                base = "06_semantic_preparation"
        else:
            mapping = {
                "semantic_structural_completion": "06a_structural_ir_completion",
                "semantic_preparation_evidence": "06b_evidence_annotation",
                "semantic_evidence_completion": "06c_evidence_completion",
                "semantic_verification": "06d_semantic_verification",
                "semantic_arbitration": "08_semantic_arbitration",
                "semantic_verification_post_arbitration": "08b_post_arbitration_verification",
                "rca_synthesis": "12_rca_synthesis",
                "fast_hypothesis_review": "13_hypothesis_review",
                "final_review": "14_wording_review",
                "fast_source_availability": "03_source_availability",
                "fast_content_classification": "04_content_classification",
                "fast_atomic_claims": "06_atomic_claims",
                "fast_requirement_language": "07_requirement_language",
            }
            base = mapping.get(stage, stage)
        return f"{case_id}:{base}" if case_id else base

    def _attach_stage_statistics(self, runtime: RuntimeRun) -> None:
        by_stage: dict[str, list[dict[str, Any]]] = {}
        for call in runtime.metrics.get("model_calls", []):
            by_stage.setdefault(call.get("stage_id") or "", []).append(call)
        for stage_id, stage in runtime.stages.items():
            calls = by_stage.get(stage_id, [])
            seconds = sum(float(x.get("request_duration_seconds") or 0.0) for x in calls)
            completion = sum(int(x.get("completion_tokens") or 0) for x in calls)
            stage.metadata["statistics"] = {
                "elapsed_seconds": round(float(stage.elapsed_ms or 0.0) / 1000.0, 6),
                "model_call_count": len(calls),
                "model_seconds": round(seconds, 6),
                "prompt_tokens": sum(int(x.get("prompt_tokens") or 0) for x in calls),
                "completion_tokens": completion,
                "reasoning_tokens": sum(int(x.get("reasoning_tokens") or 0) for x in calls),
                "reasoning_content_chars": sum(int(x.get("reasoning_content_chars") or 0) for x in calls),
                "reasoning_content_calls": sum(1 for x in calls if x.get("reasoning_content_present")),
                "thinking_requested": sorted({str(x.get("thinking_requested") or "provider_default") for x in calls}),
                "total_tokens": sum(int(x.get("total_tokens") or 0) for x in calls),
                "retries": sum(int(x.get("retries") or 0) for x in calls),
                "weighted_generation_tokens_per_second": round(completion / seconds, 3) if seconds > 0 else None,
                "models": sorted({str(x.get("model") or "") for x in calls if x.get("model")}),
                "endpoints": sorted({str(x.get("endpoint") or "") for x in calls if x.get("endpoint")}),
            }

    def _finalize_metrics(self, runtime: RuntimeRun) -> None:
        runtime.metrics["system_end"] = self.system_info.snapshot(self.storage.root)
        runtime.metrics["status"] = runtime.summary.status.value
        self._attach_stage_statistics(runtime)
        runtime.metrics["started_at"] = runtime.summary.started_at
        runtime.metrics["finished_at"] = runtime.summary.finished_at
        runtime.metrics["pipeline"] = {k: v.model_dump(mode="json") for k, v in runtime.stages.items()}
        total_run_seconds = None
        if runtime.summary.started_at and runtime.summary.finished_at:
            total_run_seconds = (_elapsed_ms(runtime.summary.started_at, runtime.summary.finished_at) or 0) / 1000.0
            runtime.metrics["total_run_seconds"] = total_run_seconds
        model_seconds = round(sum(float(x.get("request_duration_seconds") or 0.0) for x in runtime.metrics.get("model_calls", [])), 6)
        validation_seconds = 0.0
        report_seconds = 0.0
        for stage in runtime.stages.values():
            seconds = float(stage.elapsed_ms or 0.0) / 1000.0
            name = stage.name.lower()
            if "validation" in name or "consistency gate" in name:
                validation_seconds += seconds
            if "report formatter" in name or "report generation" in name:
                report_seconds += seconds
        runtime.metrics["pipeline_totals"] = {
            "llm_inference_seconds": model_seconds,
            "python_processing_seconds_estimate": round(max((total_run_seconds or 0.0) - model_seconds, 0.0), 6) if total_run_seconds is not None else None,
            "retrieval_seconds": None,
            "validation_seconds": round(validation_seconds, 6),
            "report_generation_seconds": round(report_seconds, 6),
        }
        self.storage.write_json(f"runs/{runtime.summary.run_id}/metrics.json", runtime.metrics)

    def _auto_session(self, runtime: RuntimeRun) -> None:
        payload = runtime.result or runtime.failure or {"status": runtime.summary.status.value, "message": runtime.summary.error}
        session_id = runtime.summary.run_id
        envelope = self.sessions.make_envelope(
            session_id=session_id,
            run_id=runtime.summary.run_id,
            status=runtime.summary.status.value,
            payload=payload,
            config_snapshot=runtime.config.model_dump(mode="json"),
            deployment=self.settings.deployment.model_dump(mode="json"),
            hardware=runtime.metrics.get("system_end") or runtime.metrics.get("system_start") or {},
            inference_engine={
                **runtime.config.inference.model_dump(mode="json"),
                "provider": runtime.config.primary_model.provider,
            },
        )
        runtime.summary.session_id = self.sessions.save(envelope)
        self._persist(runtime)

    def _persist(self, runtime: RuntimeRun) -> None:
        self.storage.write_json(f"runs/{runtime.summary.run_id}/metadata.json", runtime.summary.model_dump(mode="json"))
        self.storage.write_json(f"runs/{runtime.summary.run_id}/config_snapshot.json", runtime.config.model_dump(mode="json"))
        self.storage.write_json(f"runs/{runtime.summary.run_id}/pipeline.json", [x.model_dump(mode="json") for x in runtime.stages.values()])

    def _require_runtime(self, run_id: str) -> RuntimeRun:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            return self._runs[run_id]

    def get_summary(self, run_id: str) -> RunSummary:
        try:
            return self._require_runtime(run_id).summary.model_copy(deep=True)
        except KeyError:
            data = self.storage.read_json(f"runs/{run_id}/metadata.json")
            return RunSummary.model_validate(data)

    def list_runs(self) -> list[RunSummary]:
        rows: dict[str, RunSummary] = {}
        for path in (self.storage.root / "runs").glob("*/metadata.json"):
            try:
                obj = RunSummary.model_validate_json(path.read_text(encoding="utf-8"))
                rows[obj.run_id] = obj
            except Exception:
                continue
        with self._lock:
            for rid, runtime in self._runs.items():
                rows[rid] = runtime.summary.model_copy(deep=True)
        return sorted(rows.values(), key=lambda x: x.created_at, reverse=True)

    def get_pipeline(self, run_id: str) -> list[dict[str, Any]]:
        try:
            runtime = self._require_runtime(run_id)
            return [x.model_dump(mode="json") for x in runtime.stages.values()]
        except KeyError:
            return self.storage.read_json(f"runs/{run_id}/pipeline.json")

    def get_logs(self, run_id: str) -> list[dict[str, Any]]:
        try:
            return list(self._require_runtime(run_id).logs)
        except KeyError:
            path = self.storage.path(f"runs/{run_id}/logs.jsonl")
            if not path.exists(): return []
            return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def get_metrics(self, run_id: str) -> dict[str, Any]:
        try:
            runtime = self._require_runtime(run_id)
            return copy.deepcopy(runtime.metrics)
        except KeyError:
            return self.storage.read_json(f"runs/{run_id}/metrics.json")

    def get_result(self, run_id: str) -> dict[str, Any]:
        try:
            runtime = self._require_runtime(run_id)
            if runtime.result is not None: return {"status": runtime.summary.status.value, "result": runtime.result}
            if runtime.failure is not None: return {"status": runtime.summary.status.value, "failure": runtime.failure}
        except KeyError:
            pass
        result_path = self.storage.path(f"runs/{run_id}/result.json")
        if result_path.exists(): return {"status": self.get_summary(run_id).status.value, "result": json.loads(result_path.read_text(encoding="utf-8"))}
        failure_path = self.storage.path(f"runs/{run_id}/failure.json")
        if failure_path.exists(): return {"status": self.get_summary(run_id).status.value, "failure": json.loads(failure_path.read_text(encoding="utf-8"))}
        return {"status": self.get_summary(run_id).status.value}

    def get_events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        try:
            events = self._require_runtime(run_id).events
            return [copy.deepcopy(x) for x in events if int(x.get("id", 0)) > after]
        except KeyError:
            path = self.storage.path(f"runs/{run_id}/events.jsonl")
            if not path.exists(): return []
            return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and int(json.loads(x).get("id", 0)) > after]
