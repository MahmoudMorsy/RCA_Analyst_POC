from __future__ import annotations

from typing import Optional

import os

from rca_app.cancellation import CancellationToken
from rca_app.model_gateway import ModelClientSpec, ModelGateway
from rca_app.pipeline import RCAPipeline

from .backend_config import ApplicationConfig


class PipelineFactory:
    """Translate deployment/model configuration into the unchanged RCA pipeline."""

    def __init__(self, gateway: Optional[ModelGateway] = None):
        self.gateway = gateway or ModelGateway()

    @staticmethod
    def _token(env_name: str) -> str:
        return os.environ.get(env_name or "", "") if env_name else ""

    def build(self, config: ApplicationConfig, cancellation_token: CancellationToken) -> RCAPipeline:
        legacy = config.to_legacy_app_config()
        primary_cfg = config.primary_model
        small_cfg = config.small_model
        primary = self.gateway.create_client(
            ModelClientSpec(
                role="primary",
                provider=primary_cfg.provider,
                base_url=primary_cfg.endpoint,
                model=primary_cfg.model,
                temperature=primary_cfg.temperature,
                reasoning_effort=primary_cfg.reasoning_effort,
                max_tokens=primary_cfg.max_tokens,
                timeout_seconds=primary_cfg.timeout_seconds,
                api_token=self._token(primary_cfg.api_token_env),
                thinking_mode=primary_cfg.thinking_mode,
                transport=primary_cfg.transport,
            ),
            cancellation_token=cancellation_token,
        )

        def make_small(max_tokens: int, *, reasoning_effort: str = "", thinking_mode: str = "", transport: str = ""):
            if not small_cfg.model.strip():
                return None
            return self.gateway.create_client(
                ModelClientSpec(
                    role="small",
                    provider=small_cfg.provider,
                    base_url=small_cfg.endpoint,
                    model=small_cfg.model,
                    temperature=small_cfg.temperature,
                    reasoning_effort=reasoning_effort or small_cfg.reasoning_effort,
                    max_tokens=max_tokens,
                    timeout_seconds=small_cfg.timeout_seconds,
                    api_token=self._token(small_cfg.api_token_env),
                    thinking_mode=thinking_mode or small_cfg.thinking_mode,
                    transport=transport or small_cfg.transport,
                ),
                cancellation_token=cancellation_token,
            )

        intake_client = make_small(legacy.fast_intake_max_tokens) if legacy.fast_intake_enabled else None
        source_availability_client = make_small(legacy.fast_source_availability_max_tokens) if legacy.fast_intake_enabled else None
        content_classification_client = make_small(legacy.fast_content_classification_max_tokens) if legacy.fast_intake_enabled else None
        atomic_claim_client = make_small(legacy.fast_atomic_claim_max_tokens) if legacy.fast_atomic_claim_enabled else None
        requirement_language_client = make_small(legacy.fast_requirement_language_max_tokens) if legacy.fast_requirement_language_enabled else None
        semantic_preparation_client = make_small(legacy.semantic_preparation_max_tokens) if legacy.semantic_preparation_enabled else None
        if legacy.semantic_preparation_enabled and semantic_preparation_client is None:
            semantic_preparation_client = primary
        repair_client = make_small(legacy.fast_repair_max_tokens) if legacy.fast_repair_enabled else None
        hypothesis_review_client = make_small(legacy.fast_hypothesis_review_max_tokens) if legacy.fast_hypothesis_review_enabled else None
        final_review_client = (
            make_small(
                legacy.fast_final_review_max_tokens,
                reasoning_effort=legacy.fast_final_review_reasoning_effort,
                thinking_mode=legacy.fast_final_review_thinking_mode,
                transport=legacy.fast_final_review_transport,
            )
            if legacy.fast_final_review_enabled
            else None
        )

        return RCAPipeline(
            primary,
            max_repair_passes=legacy.max_repair_passes,
            repair_client=repair_client,
            intake_client=intake_client,
            final_review_client=final_review_client,
            source_availability_client=source_availability_client,
            content_classification_client=content_classification_client,
            atomic_claim_client=atomic_claim_client,
            requirement_language_client=requirement_language_client,
            hypothesis_review_client=hypothesis_review_client,
            deterministic_repair_enabled=legacy.deterministic_repair_enabled,
            fallback_to_primary_repair=legacy.fallback_to_primary_repair,
            fast_intake_enabled=legacy.fast_intake_enabled,
            fast_intake_mode=legacy.fast_intake_mode,
            fast_atomic_claim_enabled=legacy.fast_atomic_claim_enabled,
            fast_requirement_language_enabled=legacy.fast_requirement_language_enabled,
            fast_hypothesis_review_enabled=legacy.fast_hypothesis_review_enabled,
            fast_final_review_enabled=legacy.fast_final_review_enabled,
            primary_large_case_max_tokens=legacy.primary_large_case_max_tokens,
            primary_large_case_requirement_threshold=legacy.primary_large_case_requirement_threshold,
            primary_phase_a_chunk_size=legacy.primary_phase_a_chunk_size,
            semantic_preparation_client=semantic_preparation_client,
            semantic_preparation_enabled=legacy.semantic_preparation_enabled,
            semantic_arbitration_client=primary,
            semantic_arbitration_enabled=legacy.semantic_arbitration_enabled,
            rca_synthesis_enabled=legacy.rca_synthesis_enabled,
            cancellation_token=cancellation_token,
        )
