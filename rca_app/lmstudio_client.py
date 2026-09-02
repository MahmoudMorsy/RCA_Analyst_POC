from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Type

import requests
from pydantic import BaseModel

from .cancellation import AnalysisCancelled, CancellationToken
from .models import ApiStats, StructuredOutputAttempt
from .model_protocol import ModelGatewayError


class LMStudioError(ModelGatewayError):
    """Compatibility name for OpenAI-compatible transport failures."""

    pass


@dataclass
class StructuredResponse:
    parsed: BaseModel
    raw_json: str
    stats: ApiStats
    reasoning_content: str = ""
    raw_schema_valid: bool = True
    tier0_adjustments: list[dict[str, str]] = field(default_factory=list)
    transport: str = "openai-chat"
    finish_reason: str = ""
    retry_diagnostics: list[str] = field(default_factory=list)
    structured_attempts: list[StructuredOutputAttempt] = field(default_factory=list)


class LMStudioClient:
    """LM Studio client for primary structured chat and fast non-thinking structured tasks.

    v0.5.5 retains one bounded structured-output retry and strengthens its audit trail. The retry is used only when
    the API call itself completed but the final structured content is empty,
    malformed, or schema-invalid. This is intentionally different from repeatedly
    retrying network failures.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.1,
        reasoning_effort: str = "medium",
        max_tokens: int = 6144,
        timeout_seconds: int = 10800,
        api_token: str = "",
        thinking_mode: str = "provider_default",
        transport: str = "auto",
        cancellation_token: Optional[CancellationToken] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.api_token = api_token
        self.thinking_mode = thinking_mode
        self.transport = transport
        self.cancellation_token = cancellation_token
        self._active_response_lock = threading.Lock()
        self._active_response = None

    def clone(self, **overrides):
        """Create a provider-equivalent client with selected request settings changed."""
        values = {
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "api_token": self.api_token,
            "thinking_mode": self.thinking_mode,
            "transport": self.transport,
            "cancellation_token": self.cancellation_token,
        }
        values.update(overrides)
        return type(self)(**values)

    def cancel_active_request(self) -> None:
        """Best-effort immediate close of the active streaming HTTP response."""
        with self._active_response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def _set_active_response(self, response) -> None:
        with self._active_response_lock:
            self._active_response = response

    def _clear_active_response(self, response) -> None:
        with self._active_response_lock:
            if self._active_response is response:
                self._active_response = None

    def _throw_if_cancelled(self, stage: str = "LM Studio request") -> None:
        if self.cancellation_token is not None:
            self.cancellation_token.throw_if_cancelled(stage)

    @staticmethod
    def _decode_sse_line(raw_line: Any) -> str:
        """Decode SSE payload bytes explicitly as UTF-8.

        requests may otherwise default `text/event-stream` without an explicit
        charset to ISO-8859-1, which turns characters such as `→`, `–`, `ä` and
        `ß` into mojibake during cancellable streaming.
        """
        if isinstance(raw_line, bytes):
            return raw_line.decode("utf-8", errors="strict")
        return str(raw_line)

    def _stream_chat_completion(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Consume an OpenAI-compatible SSE stream so a GUI stop can abort generation.

        LM Studio documents prediction cancellation through streaming. Closing the
        active streaming response when the shared cancellation token is set makes
        cancellation cooperative instead of force-killing the Qt worker thread.
        """
        self._throw_if_cancelled("model generation")
        streamed = copy.deepcopy(payload)
        streamed["stream"] = True
        streamed["stream_options"] = {"include_usage": True}
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        finish_reason = ""
        usage: dict[str, Any] = {}
        chunks: list[dict[str, Any]] = []

        response = requests.post(
            endpoint,
            headers=self.headers,
            json=streamed,
            timeout=self.timeout_seconds,
            stream=True,
        )
        self._set_active_response(response)
        try:
            response.raise_for_status()
            for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
                if self.cancellation_token is not None and self.cancellation_token.cancelled:
                    response.close()
                    self._throw_if_cancelled("model generation")
                if not raw_line:
                    continue
                line = self._decode_sse_line(raw_line).strip()
                if line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                if not line.startswith("{"):
                    continue
                chunk = json.loads(line)
                chunks.append(chunk)
                if chunk.get("usage"):
                    usage = chunk.get("usage") or usage
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0] or {}
                delta = choice.get("delta") or {}
                content = delta.get("content", "")
                reasoning = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                if isinstance(content, list):
                    content = "".join(
                        str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content
                    )
                if content:
                    content_parts.append(str(content))
                if reasoning:
                    reasoning_parts.append(str(reasoning))
                if choice.get("finish_reason"):
                    finish_reason = str(choice.get("finish_reason") or "")
        except Exception:
            if self.cancellation_token is not None and self.cancellation_token.cancelled:
                self._throw_if_cancelled("model generation")
            raise
        finally:
            response.close()
            self._clear_active_response(response)

        self._throw_if_cancelled("model generation")
        return {
            "model": self.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "".join(content_parts),
                    "reasoning_content": "".join(reasoning_parts),
                },
                "finish_reason": finish_reason,
            }],
            "usage": usage,
            "stream_chunks": chunks,
        }

    def _stream_text_completion(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Consume a legacy /completions SSE stream with cooperative cancellation."""
        self._throw_if_cancelled("fast-model generation")
        streamed = copy.deepcopy(payload)
        streamed["stream"] = True
        streamed["stream_options"] = {"include_usage": True}
        text_parts: list[str] = []
        finish_reason = ""
        usage: dict[str, Any] = {}
        chunks: list[dict[str, Any]] = []

        response = requests.post(
            endpoint,
            headers=self.headers,
            json=streamed,
            timeout=self.timeout_seconds,
            stream=True,
        )
        self._set_active_response(response)
        try:
            response.raise_for_status()
            for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
                if self.cancellation_token is not None and self.cancellation_token.cancelled:
                    response.close()
                    self._throw_if_cancelled("fast-model generation")
                if not raw_line:
                    continue
                line = self._decode_sse_line(raw_line).strip()
                if line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                if not line.startswith("{"):
                    continue
                chunk = json.loads(line)
                chunks.append(chunk)
                if chunk.get("usage"):
                    usage = chunk.get("usage") or usage
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0] or {}
                if choice.get("text"):
                    text_parts.append(str(choice.get("text") or ""))
                if choice.get("finish_reason"):
                    finish_reason = str(choice.get("finish_reason") or "")
        except Exception:
            if self.cancellation_token is not None and self.cancellation_token.cancelled:
                self._throw_if_cancelled("fast-model generation")
            raise
        finally:
            response.close()
            self._clear_active_response(response)

        self._throw_if_cancelled("fast-model generation")
        return {
            "model": self.model,
            "choices": [{"index": 0, "text": "".join(text_parts), "finish_reason": finish_reason}],
            "usage": usage,
            "stream_chunks": chunks,
        }

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def model_catalog(self) -> list[dict[str, Any]]:
        """Return provider-advertised model metadata without interpreting it."""
        url = f"{self.base_url}/models"
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            return [dict(item) for item in data.get("data", []) if isinstance(item, dict)]
        except Exception as exc:
            raise LMStudioError(f"Could not query model catalog at {url}: {exc}") from exc

    def list_models(self) -> list[str]:
        return [str(item["id"]) for item in self.model_catalog() if item.get("id")]

    def test_connection(self) -> tuple[bool, str]:
        models = self.list_models()
        if not models:
            return True, "LM Studio server is reachable, but no models were returned."
        return True, f"LM Studio server reachable. {len(models)} model(s) available."

    def resolve_transport(self) -> str:
        if self.transport != "auto":
            return self.transport
        if self.thinking_mode == "off" and "qwen3.5" in self.model.lower():
            return "qwen35-manual"
        return "openai-chat"

    def structured_repair(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        schema_name: str,
    ) -> StructuredResponse:
        transport = self.resolve_transport()
        if transport == "qwen35-manual":
            return self._manual_qwen35_completion(system_prompt, user_prompt, response_model)
        return self.structured_chat(system_prompt, user_prompt, response_model, schema_name)

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        schema_name: str,
        max_tokens_override: Optional[int] = None,
    ) -> StructuredResponse:
        schema = response_model.model_json_schema()
        endpoint = f"{self.base_url}/chat/completions"
        base_max_tokens = max(1, int(max_tokens_override or self.max_tokens))

        total_elapsed = 0.0
        total_prompt = 0
        total_completion = 0
        total_reasoning = 0
        total_tokens = 0
        http_retries = 0
        retry_diagnostics: list[str] = []
        structured_attempts: list[StructuredOutputAttempt] = []
        last_raw = ""
        last_reasoning = ""
        last_finish_reason = ""
        last_api_response = ""

        for structured_attempt in range(2):
            retry_note = ""
            effective_max_tokens = base_max_tokens
            effective_reasoning = self.reasoning_effort
            if structured_attempt == 1:
                # Keep recovery bounded and output-oriented. v0.7.0 can supply a
                # larger per-call budget (for example 16k on TC12/TC21-class inputs);
                # retries keep that budget rather than growing it again. Normal-size
                # calls retain only modest headroom, while reasoning effort is reduced.
                if base_max_tokens < 8192:
                    effective_max_tokens = min(base_max_tokens + 1024, 8192)
                if effective_reasoning and effective_reasoning not in {"provider_default", "low"}:
                    effective_reasoning = "low"
                retry_note = (
                    "\n\nSTRUCTURED-OUTPUT RETRY: The previous completed call did not yield a usable final JSON object. "
                    "Preserve the same engineering semantics. Keep internal reasoning short and return the complete requested JSON schema directly; "
                    "do not spend the recovery budget restating the case."
                )

            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt + retry_note},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "max_tokens": effective_max_tokens,
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            }
            if effective_reasoning and effective_reasoning != "provider_default":
                payload["reasoning_effort"] = effective_reasoning

            start = time.perf_counter()
            attempt_http_retries = 0
            try:
                self._throw_if_cancelled("primary structured request")
                if self.cancellation_token is not None:
                    data = self._stream_chat_completion(endpoint, payload)
                else:
                    response = requests.post(endpoint, headers=self.headers, json=payload, timeout=self.timeout_seconds)
                    if response.status_code >= 400 and "reasoning_effort" in payload:
                        body = response.text.lower()
                        if "reasoning" in body or response.status_code in (400, 422):
                            http_retries += 1
                            attempt_http_retries += 1
                            payload.pop("reasoning_effort", None)
                            response = requests.post(endpoint, headers=self.headers, json=payload, timeout=self.timeout_seconds)
                    response.raise_for_status()
                    data = response.json()
            except AnalysisCancelled:
                raise
            except requests.RequestException as exc:
                if self.cancellation_token is not None and self.cancellation_token.cancelled:
                    self._throw_if_cancelled("primary structured request")
                elapsed = time.perf_counter() - start
                total_elapsed += elapsed
                attempt_stats = ApiStats(
                    elapsed_seconds=elapsed, retries=attempt_http_retries, endpoint=endpoint, model=self.model
                )
                structured_attempts.append(StructuredOutputAttempt(
                    attempt_index=structured_attempt + 1, stats=attempt_stats, error=str(exc),
                    retry_reason="Network/request failure; no structured-output retry was substituted."
                ))
                stats = ApiStats(
                    elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                    total_tokens=total_tokens, reasoning_tokens=total_reasoning,
                    retries=http_retries + structured_attempt, endpoint=endpoint, model=self.model,
                )
                raise LMStudioError(
                    f"LM Studio request failed: {exc}", stats=stats, transport="openai-chat",
                    retry_diagnostics=retry_diagnostics, structured_attempts=structured_attempts,
                ) from exc
            except Exception as exc:
                if self.cancellation_token is not None and self.cancellation_token.cancelled:
                    self._throw_if_cancelled("primary structured request")
                elapsed = time.perf_counter() - start
                total_elapsed += elapsed
                attempt_stats = ApiStats(
                    elapsed_seconds=elapsed, retries=attempt_http_retries, endpoint=endpoint, model=self.model
                )
                structured_attempts.append(StructuredOutputAttempt(
                    attempt_index=structured_attempt + 1, stats=attempt_stats, error=str(exc)
                ))
                stats = ApiStats(
                    elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                    total_tokens=total_tokens, reasoning_tokens=total_reasoning,
                    retries=http_retries + structured_attempt, endpoint=endpoint, model=self.model,
                )
                raise LMStudioError(
                    f"LM Studio response could not be decoded: {exc}", stats=stats, transport="openai-chat",
                    retry_diagnostics=retry_diagnostics, structured_attempts=structured_attempts,
                ) from exc

            elapsed = time.perf_counter() - start
            total_elapsed += elapsed
            last_api_response = json.dumps(data, ensure_ascii=False)
            usage = data.get("usage", {}) or {}
            details = usage.get("completion_tokens_details", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            used_total_tokens = int(usage.get("total_tokens", 0) or 0)
            reasoning_tokens = int(details.get("reasoning_tokens", 0) or 0)
            total_prompt += prompt_tokens
            total_completion += completion_tokens
            total_tokens += used_total_tokens
            total_reasoning += reasoning_tokens
            attempt_stats = ApiStats(
                elapsed_seconds=elapsed, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=used_total_tokens, reasoning_tokens=reasoning_tokens, retries=attempt_http_retries,
                endpoint=endpoint, model=self.model,
            )

            try:
                choice = data["choices"][0]
                message = choice["message"]
                last_finish_reason = str(choice.get("finish_reason", "") or "")
                raw = message.get("content", "")
                last_reasoning = message.get("reasoning_content", "") or ""
                if isinstance(raw, list):
                    raw = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in raw)
                last_raw = str(raw or "")
                if not last_raw.strip():
                    raise ValueError("assistant content is empty")
                parsed_json = json.loads(last_raw)
                parsed = response_model.model_validate(parsed_json)
            except Exception as exc:
                diagnostic = (
                    f"structured attempt {structured_attempt + 1}: {type(exc).__name__}: {exc}; "
                    f"finish_reason={last_finish_reason or '<none>'}; content_chars={len(last_raw)}; "
                    f"reasoning_chars={len(last_reasoning)}"
                )
                retry_diagnostics.append(diagnostic)
                structured_attempts.append(StructuredOutputAttempt(
                    attempt_index=structured_attempt + 1, raw_llm_json=last_raw, raw_api_response=last_api_response,
                    reasoning_content=last_reasoning, finish_reason=last_finish_reason, stats=attempt_stats, error=str(exc),
                    retry_reason=(
                        (
                            "Output token exhaustion (finish_reason=length); one bounded recovery attempt will keep the configured output budget, reduce reasoning effort, and request the complete JSON directly."
                            if last_finish_reason == "length"
                            else "Invalid/empty structured output; one bounded recovery attempt will be made with lower reasoning effort and the configured output budget."
                        )
                        if structured_attempt == 0 else ""
                    ),
                ))
                if structured_attempt == 0:
                    continue
                stats = ApiStats(
                    elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                    total_tokens=total_tokens, reasoning_tokens=total_reasoning, retries=http_retries + 1,
                    endpoint=endpoint, model=self.model,
                )
                preview = last_api_response[:3500]
                raise LMStudioError(
                    "LM Studio returned an invalid structured response after one bounded retry: "
                    f"{exc}\nResponse preview: {preview}", raw_json=last_raw or last_api_response,
                    reasoning_content=last_reasoning, stats=stats, finish_reason=last_finish_reason,
                    transport="openai-chat", retry_diagnostics=retry_diagnostics, raw_api_response=last_api_response,
                    structured_attempts=structured_attempts,
                ) from exc

            structured_attempts.append(StructuredOutputAttempt(
                attempt_index=structured_attempt + 1, raw_llm_json=last_raw, raw_api_response=last_api_response,
                reasoning_content=last_reasoning, finish_reason=last_finish_reason, stats=attempt_stats,
            ))
            stats = ApiStats(
                elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                total_tokens=total_tokens, reasoning_tokens=total_reasoning, retries=http_retries + structured_attempt,
                endpoint=endpoint, model=self.model,
            )
            return StructuredResponse(
                parsed=parsed, raw_json=last_raw, stats=stats, reasoning_content=last_reasoning,
                raw_schema_valid=True, tier0_adjustments=[], transport="openai-chat",
                finish_reason=last_finish_reason, retry_diagnostics=retry_diagnostics,
                structured_attempts=structured_attempts,
            )

        raise AssertionError("structured chat retry loop exhausted unexpectedly")

    def _manual_qwen35_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
    ) -> StructuredResponse:
        endpoint = f"{self.base_url}/completions"
        total_elapsed = 0.0
        total_prompt = 0
        total_completion = 0
        total_tokens = 0
        retry_diagnostics: list[str] = []
        structured_attempts: list[StructuredOutputAttempt] = []
        last_raw = ""
        last_finish_reason = ""
        last_api_response = ""

        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        schema_instruction = (
            "\n\nSTRICT STRUCTURED OUTPUT CONTRACT:\n"
            "Return exactly one JSON object and nothing else. Do not use YAML, Markdown, prose, comments, or code fences. "
            "The object must validate against this JSON Schema exactly:\n" + schema_json
        )

        for structured_attempt in range(2):
            retry_note = ""
            if structured_attempt == 1:
                retry_note = (
                    "\nThe previous completed structured output was not valid JSON for the required schema. "
                    "Return exactly one complete JSON object matching the schema above; do not add prose, YAML, labels, or extra fields."
                )
            rendered = (
                "<|im_start|>system\n" + (system_prompt.strip() + schema_instruction + retry_note) + "<|im_end|>\n"
                "<|im_start|>user\n" + user_prompt.strip() + "<|im_end|>\n"
                "<|im_start|>assistant\n<think>\n\n</think>\n\n"
            )
            payload = {
                "model": self.model,
                "prompt": rendered,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
                "stop": ["<|im_end|>"],
            }
            start = time.perf_counter()
            try:
                self._throw_if_cancelled("fast-model structured request")
                if self.cancellation_token is not None:
                    data = self._stream_text_completion(endpoint, payload)
                else:
                    r = requests.post(endpoint, headers=self.headers, json=payload, timeout=self.timeout_seconds)
                    r.raise_for_status()
                    data = r.json()
            except AnalysisCancelled:
                raise
            except requests.RequestException as exc:
                if self.cancellation_token is not None and self.cancellation_token.cancelled:
                    self._throw_if_cancelled("fast-model structured request")
                elapsed = time.perf_counter() - start
                total_elapsed += elapsed
                attempt_stats = ApiStats(elapsed_seconds=elapsed, endpoint=endpoint, model=self.model)
                structured_attempts.append(StructuredOutputAttempt(
                    attempt_index=structured_attempt + 1, stats=attempt_stats, error=str(exc)
                ))
                stats = ApiStats(
                    elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                    total_tokens=total_tokens, reasoning_tokens=0, retries=structured_attempt, endpoint=endpoint, model=self.model,
                )
                raise LMStudioError(
                    f"LM Studio manual Qwen3.5 completion failed: {exc}", stats=stats, transport="qwen35-manual",
                    retry_diagnostics=retry_diagnostics, structured_attempts=structured_attempts,
                ) from exc
            elapsed = time.perf_counter() - start
            total_elapsed += elapsed
            last_api_response = json.dumps(data, ensure_ascii=False)
            usage = data.get("usage", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            used_total_tokens = int(usage.get("total_tokens", 0) or 0)
            total_prompt += prompt_tokens
            total_completion += completion_tokens
            total_tokens += used_total_tokens
            attempt_stats = ApiStats(
                elapsed_seconds=elapsed, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=used_total_tokens, reasoning_tokens=0, endpoint=endpoint, model=self.model,
            )

            raw_schema_valid = True
            adjustments: list[dict[str, str]] = []
            parse_error: Optional[Exception] = None
            recovered_suffix = ""
            try:
                choice = data["choices"][0]
                last_finish_reason = str(choice.get("finish_reason", "") or "")
                last_raw = str(choice.get("text", ""))
                try:
                    parsed_json = self._parse_json_object_text(last_raw, response_model=response_model)
                except Exception as exc:
                    parse_error = exc
                    if structured_attempt == 1:
                        parsed_json, recovered_suffix = self._recover_terminal_json_object(last_raw)
                        raw_schema_valid = False
                        adjustments.append({
                            "path": "$",
                            "before": "terminal JSON delimiters truncated",
                            "after": f"appended {recovered_suffix!r}",
                            "reason": "After the one bounded model retry, appended only mechanically missing terminal JSON delimiters; no semantic token or field content was changed.",
                        })
                    else:
                        raise
                try:
                    response_model.model_validate(parsed_json)
                except Exception:
                    raw_schema_valid = False

                sanitized, wrapper_notes = self._sanitize_to_schema_top_level(parsed_json, response_model)
                normalized, alias_notes = self._normalize_safe_aliases(sanitized)
                adjustments.extend(wrapper_notes)
                adjustments.extend(alias_notes)
                parsed = response_model.model_validate(normalized)
            except Exception as exc:
                diagnostic = (
                    f"structured attempt {structured_attempt + 1}: {type(exc).__name__}: {exc}; "
                    f"finish_reason={last_finish_reason or '<none>'}; content_chars={len(last_raw)}"
                )
                retry_diagnostics.append(diagnostic)
                structured_attempts.append(StructuredOutputAttempt(
                    attempt_index=structured_attempt + 1, raw_llm_json=last_raw, raw_api_response=last_api_response,
                    finish_reason=last_finish_reason, stats=attempt_stats, error=str(exc),
                    retry_reason=(
                        "Malformed fast-model JSON; one bounded cheap retry will request the same structured schema as JSON only."
                        if structured_attempt == 0 else ""
                    ),
                ))
                if structured_attempt == 0:
                    continue
                stats = ApiStats(
                    elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                    total_tokens=total_tokens, reasoning_tokens=0, retries=1, endpoint=endpoint, model=self.model,
                )
                raise LMStudioError(
                    "Manual Qwen3.5 completion returned invalid structured JSON after one bounded retry: "
                    f"{exc}\nResponse preview: {last_api_response[:3500]}", raw_json=last_raw or last_api_response,
                    reasoning_content="", stats=stats, finish_reason=last_finish_reason, transport="qwen35-manual",
                    retry_diagnostics=retry_diagnostics, raw_api_response=last_api_response,
                    structured_attempts=structured_attempts,
                ) from exc

            structured_attempts.append(StructuredOutputAttempt(
                attempt_index=structured_attempt + 1, raw_llm_json=last_raw, raw_api_response=last_api_response,
                finish_reason=last_finish_reason, stats=attempt_stats,
                error=(str(parse_error) if parse_error is not None and recovered_suffix else ""),
                retry_reason=(
                    "Recovered after the bounded retry by appending only missing terminal JSON delimiters."
                    if recovered_suffix else ""
                ),
            ))
            stats = ApiStats(
                elapsed_seconds=total_elapsed, prompt_tokens=total_prompt, completion_tokens=total_completion,
                total_tokens=total_tokens, reasoning_tokens=0, retries=structured_attempt, endpoint=endpoint, model=self.model,
            )
            return StructuredResponse(
                parsed=parsed, raw_json=last_raw, stats=stats, reasoning_content="", raw_schema_valid=raw_schema_valid,
                tier0_adjustments=adjustments, transport="qwen35-manual", finish_reason=last_finish_reason,
                retry_diagnostics=retry_diagnostics, structured_attempts=structured_attempts,
            )

        raise AssertionError("manual completion retry loop exhausted unexpectedly")

    @staticmethod
    def _parse_json_object_text(raw: str, response_model: Optional[Type[BaseModel]] = None) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        if text.startswith("["):
            # Safe schema-envelope normalization for single-list response models.
            # No semantic content is added/changed: the bare list is wrapped under
            # the schema's sole array property (e.g. {"claims": [...]}).
            try:
                parsed_list = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LMStudioError(f"Invalid top-level JSON array in model output: {exc}. Preview: {text[:1200]}") from exc
            if not isinstance(parsed_list, list) or response_model is None:
                raise LMStudioError("Structured model output must be a JSON object.")
            props = response_model.model_json_schema().get("properties") or {}
            array_keys = [k for k, v in props.items() if isinstance(v, dict) and v.get("type") == "array"]
            if len(props) == 1 and len(array_keys) == 1:
                return {array_keys[0]: parsed_list}
            raise LMStudioError(
                "Bare top-level JSON arrays are accepted only for a response schema with exactly one array field."
            )
        if not text.startswith("{"):
            raise LMStudioError(
                "Structured model output must start with a top-level JSON object; embedded JSON inside prose/YAML is not accepted. "
                f"Preview: {text[:1200]}"
            )
        decoder = json.JSONDecoder()
        try:
            parsed, end = decoder.raw_decode(text)
        except json.JSONDecodeError as exc:
            raise LMStudioError(f"Invalid top-level JSON object in model output: {exc}. Preview: {text[:1200]}") from exc
        if not isinstance(parsed, dict):
            raise LMStudioError("Structured model output must be a JSON object.")
        trailing = text[end:].strip()
        if trailing:
            raise LMStudioError(
                "Structured model output contained non-JSON trailing content after the top-level object. "
                f"Trailing preview: {trailing[:600]}"
            )
        return parsed

    @staticmethod
    def _recover_terminal_json_object(raw: str) -> tuple[dict[str, Any], str]:
        """Recover only JSON truncated by missing terminal ``]``/``}`` delimiters.

        This intentionally does not insert commas, repair strings, rename fields or
        otherwise guess semantics. It is used only after the bounded fast-model
        retry has already been consumed.
        """
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        if not text.startswith("{"):
            raise ValueError("Terminal-only JSON recovery requires output to begin with the top-level JSON object; embedded JSON is unsafe to recover.")

        stack: list[str] = []
        pairs = {"{": "}", "[": "]"}
        reverse = {"}": "{", "]": "["}
        in_string = False
        escaped = False
        for ch in text:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in pairs:
                stack.append(ch)
            elif ch in reverse:
                if not stack or stack[-1] != reverse[ch]:
                    raise ValueError("JSON contains mismatched closing delimiters; terminal-only recovery is unsafe.")
                stack.pop()
        if in_string:
            raise ValueError("JSON ends inside a quoted string; terminal-only recovery is unsafe.")
        if not stack:
            raise ValueError("JSON is not missing terminal delimiters; no safe terminal-only recovery applies.")
        suffix = "".join(pairs[ch] for ch in reversed(stack))
        recovered = json.loads(text + suffix)
        if not isinstance(recovered, dict):
            raise ValueError("Recovered JSON is not an object.")
        return recovered, suffix

    @staticmethod
    def _sanitize_to_schema_top_level(payload: dict[str, Any], response_model: Type[BaseModel]):
        if not isinstance(payload, dict):
            return payload, []
        out = copy.deepcopy(payload)
        allowed = set((response_model.model_json_schema().get("properties") or {}).keys())
        notes: list[dict[str, str]] = []
        for key in list(out.keys()):
            if key in allowed:
                continue
            out.pop(key, None)
            notes.append({
                "path": key,
                "before": "present",
                "after": "removed",
                "reason": "Extra top-level context echo not permitted by the requested response schema.",
            })
        return out, notes

    @staticmethod
    def _normalize_safe_aliases(payload: dict[str, Any]):
        """Normalize only the mechanically unambiguous element alias used in testing."""
        out = copy.deepcopy(payload)
        notes: list[dict[str, str]] = []

        def walk(obj: Any, path: str = ""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    here = f"{path}.{key}" if path else key
                    if key == "element" and value == "INTERVAL_STATE":
                        obj[key] = "OBSERVATION_INTERVAL"
                        notes.append({
                            "path": here,
                            "before": "INTERVAL_STATE",
                            "after": "OBSERVATION_INTERVAL",
                            "reason": "Observation type token used where RequirementElementType was required.",
                        })
                    else:
                        walk(value, here)
            elif isinstance(obj, list):
                for i, value in enumerate(obj):
                    walk(value, f"{path}[{i}]")

        walk(out)
        return out, notes
