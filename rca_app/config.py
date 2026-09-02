from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIG_DIR = Path.home() / ".rca_analyst_poc"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = ""
    temperature: float = 0.1
    reasoning_effort: str = "medium"
    max_tokens: int = 6144
    # v0.7.0 primary deep-analysis decomposition. Normal cases retain the
    # existing budget; large Phase-A chunks can use a much larger completion
    # allowance so reasoning does not starve the required structured JSON.
    primary_large_case_max_tokens: int = 16000
    primary_large_case_requirement_threshold: int = 8
    primary_phase_a_chunk_size: int = 6
    # One repair round may contain several sequential field-level actions.
    max_repair_passes: int = 1
    request_timeout_seconds: int = 10800

    # v0.8 semantic-compiler architecture. Semantic preparation is mandatory
    # for production runs; when no fast model is configured the GUI/CLI falls
    # back to the primary model for this one compilation call rather than asking
    # Python to interpret requirement language.
    semantic_preparation_enabled: bool = True
    semantic_preparation_max_tokens: int = 6000
    semantic_arbitration_enabled: bool = True
    rca_synthesis_enabled: bool = True

    # v0.6.x shared fast-model services (intake, narrow repair, final wording review).
    deterministic_repair_enabled: bool = True
    fast_intake_enabled: bool = True
    fast_intake_mode: str = "auto"
    fast_intake_max_tokens: int = 2200  # legacy combined-intake fallback budget
    fast_source_availability_max_tokens: int = 900
    fast_content_classification_max_tokens: int = 2800
    fast_atomic_claim_enabled: bool = False  # deprecated by v0.8 semantic preparation
    fast_atomic_claim_max_tokens: int = 1800
    fast_requirement_language_enabled: bool = False  # deprecated by v0.8 semantic preparation
    fast_requirement_language_max_tokens: int = 2400
    fast_repair_enabled: bool = True
    fast_final_review_enabled: bool = False  # optional wording audit only in v0.8
    fast_hypothesis_review_enabled: bool = True
    fast_hypothesis_review_max_tokens: int = 1200
    fast_final_review_max_tokens: int = 1200
    fast_final_review_reasoning_effort: str = "provider_default"
    fast_final_review_thinking_mode: str = "off"
    fast_final_review_transport: str = "auto"
    fast_repair_model: str = ""
    fast_repair_temperature: float = 0.0
    fast_repair_reasoning_effort: str = "provider_default"
    fast_repair_thinking_mode: str = "off"
    fast_repair_transport: str = "auto"
    fast_repair_max_tokens: int = 1400
    fallback_to_primary_repair: bool = True

    # GUI appearance.
    theme: str = "dark"

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            allowed = {k: v for k, v in data.items() if k in cls.__annotations__}
            cfg = cls(**allowed)
            # Preserve old user choices while migrating the v0.5.0 defaults to
            # the settings actually validated by the fast-repair benchmark.
            if "fast_repair_thinking_mode" not in data:
                cfg.fast_repair_thinking_mode = "off"
            if "fast_repair_transport" not in data:
                cfg.fast_repair_transport = "auto"
            legacy_v064_review_defaults = (
                data.get("fast_final_review_reasoning_effort") == "low"
                and data.get("fast_final_review_thinking_mode") == "provider_default"
                and data.get("fast_final_review_transport") == "openai-chat"
            )
            if "fast_final_review_reasoning_effort" not in data or legacy_v064_review_defaults:
                cfg.fast_final_review_reasoning_effort = "provider_default"
            if "fast_final_review_thinking_mode" not in data or legacy_v064_review_defaults:
                cfg.fast_final_review_thinking_mode = "off"
            if "fast_final_review_transport" not in data or legacy_v064_review_defaults:
                cfg.fast_final_review_transport = "auto"
            if data.get("fast_repair_max_tokens") == 2048:
                cfg.fast_repair_max_tokens = 1400
            if data.get("fast_repair_reasoning_effort") == "low":
                cfg.fast_repair_reasoning_effort = "provider_default"
            return cfg
        except Exception:
            return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
