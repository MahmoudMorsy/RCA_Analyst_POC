from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .cancellation import CancellationToken
from .lmstudio_client import LMStudioClient
from .model_protocol import ModelClient


@dataclass(frozen=True)
class ModelClientSpec:
    role: str
    provider: str
    base_url: str
    model: str
    temperature: float = 0.1
    reasoning_effort: str = "provider_default"
    max_tokens: int = 6144
    timeout_seconds: int = 10800
    api_token: str = ""
    thinking_mode: str = "provider_default"
    transport: str = "auto"


class ModelGateway:
    """Hardware/provider abstraction used by deployment code to obtain RCA model clients.

    The RCA core receives only the provider-neutral ``ModelClient`` protocol.  This
    gateway is the only application layer that knows how an OpenAI-compatible
    endpoint is implemented or where it is hosted.
    """

    SUPPORTED_PROVIDERS = {"openai-compatible", "lmstudio", "llama.cpp", "vllm"}

    def create_client(
        self,
        spec: ModelClientSpec,
        *,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ModelClient:
        provider = (spec.provider or "openai-compatible").strip().lower()
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported model provider: {spec.provider}")
        # LM Studio, llama.cpp and vLLM all expose an OpenAI-compatible surface
        # for the request shapes used by the validated RCA pipeline.  The proven
        # transport implementation is therefore retained behind this abstraction.
        return LMStudioClient(
            base_url=spec.base_url,
            model=spec.model,
            temperature=spec.temperature,
            reasoning_effort=spec.reasoning_effort,
            max_tokens=spec.max_tokens,
            timeout_seconds=spec.timeout_seconds,
            api_token=spec.api_token,
            thinking_mode=spec.thinking_mode,
            transport=spec.transport,
            cancellation_token=cancellation_token,
        )

    def list_models(self, spec: ModelClientSpec) -> list[str]:
        return self.create_client(spec).list_models()

    def test_connection(self, spec: ModelClientSpec) -> tuple[bool, str]:
        return self.create_client(spec).test_connection()
