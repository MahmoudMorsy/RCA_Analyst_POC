from __future__ import annotations

from typing import Any, Optional, Protocol, Type, runtime_checkable

from pydantic import BaseModel

from .models import StructuredOutputAttempt, ApiStats


class ModelGatewayError(RuntimeError):
    """Provider-neutral inference failure persisted by the RCA pipeline."""

    def __init__(
        self,
        message: str,
        *,
        raw_json: str = "",
        reasoning_content: str = "",
        stats: Optional[ApiStats] = None,
        finish_reason: str = "",
        transport: str = "",
        retry_diagnostics: Optional[list[str]] = None,
        raw_api_response: str = "",
        structured_attempts: Optional[list[StructuredOutputAttempt]] = None,
    ) -> None:
        super().__init__(message)
        self.raw_json = raw_json
        self.reasoning_content = reasoning_content
        self.stats = stats or ApiStats()
        self.finish_reason = finish_reason
        self.transport = transport
        self.retry_diagnostics = list(retry_diagnostics or [])
        self.raw_api_response = raw_api_response
        self.structured_attempts = list(structured_attempts or [])


@runtime_checkable
class ModelClient(Protocol):
    base_url: str
    model: str
    temperature: float
    reasoning_effort: str
    max_tokens: int
    timeout_seconds: int
    api_token: str
    thinking_mode: str
    transport: str

    def list_models(self) -> list[str]: ...
    def model_catalog(self) -> list[dict[str, Any]]: ...
    def test_connection(self) -> tuple[bool, str]: ...
    def resolve_transport(self) -> str: ...
    def cancel_active_request(self) -> None: ...
    def clone(self, **overrides: Any) -> "ModelClient": ...
    def structured_chat(self, *args: Any, **kwargs: Any): ...
    def structured_repair(self, *args: Any, **kwargs: Any): ...
