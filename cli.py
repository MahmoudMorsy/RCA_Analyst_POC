from __future__ import annotations

import argparse
from pathlib import Path

from rca_app.config import AppConfig
from rca_app.lmstudio_client import LMStudioClient
from rca_app.pipeline import RCAPipeline


def main() -> int:
    p = argparse.ArgumentParser(description="Run the RCA analysis pipeline without the GUI.")
    p.add_argument("case", type=Path, help="Text/Markdown file containing the complete current case")
    p.add_argument("--model", default="", help="Primary LM Studio model ID; defaults to saved GUI config")
    p.add_argument("--fast-model", "--fast-repair-model", dest="fast_repair_model", default="", help="Optional shared Qwen3.5-class model ID for intake/repair/final review; defaults to saved GUI config")
    p.add_argument("--disable-fast-intake", action="store_true")
    p.add_argument("--disable-semantic-preparation", action="store_true", help="Disable the v0.8 LLM semantic compiler (legacy/diagnostic use only)")
    p.add_argument("--disable-semantic-arbitration", action="store_true", help="Do not escalate materially unresolved semantics to the primary model")
    p.add_argument("--disable-rca-synthesis", action="store_true", help="Skip conditional deep RCA synthesis even when mechanism evidence exists")
    p.add_argument("--fast-intake-mode", choices=["auto", "always", "off"], default="")
    p.add_argument("--disable-fast-repair", action="store_true")
    p.add_argument("--disable-fast-atomic-claims", action="store_true")
    p.add_argument("--disable-fast-requirement-language", action="store_true")
    p.add_argument("--disable-fast-hypothesis-review", action="store_true")
    p.add_argument("--disable-fast-final-review", action="store_true")
    p.add_argument("--disable-deterministic-repair", action="store_true")
    p.add_argument("--no-primary-repair-fallback", action="store_true")
    p.add_argument("--base-url", default="", help="Default: saved config / http://127.0.0.1:1234/v1")
    p.add_argument("--reasoning", choices=["provider_default", "low", "medium", "xhigh"], default="")
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--repairs", type=int, default=None, help="Maximum repair rounds; each round may contain multiple sequential field-level actions")
    p.add_argument("--output", type=Path, default=Path("RCA_Report.md"))
    args = p.parse_args()

    cfg = AppConfig.load()
    model = args.model or cfg.model
    if not model:
        p.error("No model specified and no saved GUI model is available. Use --model.")

    base_url = args.base_url or cfg.base_url
    client = LMStudioClient(
        base_url=base_url,
        model=model,
        temperature=cfg.temperature if args.temperature is None else args.temperature,
        reasoning_effort=args.reasoning or cfg.reasoning_effort,
        max_tokens=cfg.max_tokens if args.max_tokens is None else args.max_tokens,
        timeout_seconds=cfg.request_timeout_seconds,
    )

    fast_model = args.fast_repair_model or cfg.fast_repair_model

    def make_fast(
        max_tokens: int,
        reasoning_effort: str = "",
        thinking_mode: str = "",
        transport: str = "",
    ):
        if not fast_model:
            return None
        return LMStudioClient(
            base_url=base_url,
            model=fast_model,
            temperature=cfg.fast_repair_temperature,
            reasoning_effort=reasoning_effort or cfg.fast_repair_reasoning_effort,
            max_tokens=max_tokens,
            timeout_seconds=cfg.request_timeout_seconds,
            thinking_mode=thinking_mode or cfg.fast_repair_thinking_mode,
            transport=transport or cfg.fast_repair_transport,
        )

    intake_enabled = cfg.fast_intake_enabled and not args.disable_fast_intake
    semantic_preparation_enabled = cfg.semantic_preparation_enabled and not args.disable_semantic_preparation
    repair_enabled = cfg.fast_repair_enabled and not args.disable_fast_repair
    review_enabled = cfg.fast_final_review_enabled and not args.disable_fast_final_review
    intake_client = make_fast(cfg.fast_intake_max_tokens) if intake_enabled else None
    source_availability_client = make_fast(cfg.fast_source_availability_max_tokens) if intake_enabled else None
    content_classification_client = make_fast(cfg.fast_content_classification_max_tokens) if intake_enabled else None
    atomic_enabled = cfg.fast_atomic_claim_enabled and not args.disable_fast_atomic_claims
    requirement_language_enabled = cfg.fast_requirement_language_enabled and not args.disable_fast_requirement_language
    hypothesis_review_enabled = cfg.fast_hypothesis_review_enabled and not args.disable_fast_hypothesis_review
    atomic_claim_client = make_fast(cfg.fast_atomic_claim_max_tokens) if atomic_enabled else None
    requirement_language_client = make_fast(cfg.fast_requirement_language_max_tokens) if requirement_language_enabled else None
    hypothesis_review_client = make_fast(cfg.fast_hypothesis_review_max_tokens) if hypothesis_review_enabled else None
    semantic_preparation_client = make_fast(cfg.semantic_preparation_max_tokens) if semantic_preparation_enabled else None
    # Language compilation must remain LLM-owned. If no fast model is configured,
    # use the primary model for this one preparation call rather than falling back
    # to deterministic language parsing.
    if semantic_preparation_enabled and semantic_preparation_client is None:
        semantic_preparation_client = client
    repair_client = make_fast(cfg.fast_repair_max_tokens) if repair_enabled else None
    final_review_client = (
        make_fast(
            cfg.fast_final_review_max_tokens,
            reasoning_effort=cfg.fast_final_review_reasoning_effort,
            thinking_mode=cfg.fast_final_review_thinking_mode,
            transport=cfg.fast_final_review_transport,
        )
        if review_enabled else None
    )

    pipeline = RCAPipeline(
        client,
        max_repair_passes=cfg.max_repair_passes if args.repairs is None else args.repairs,
        repair_client=repair_client,
        intake_client=intake_client,
        final_review_client=final_review_client,
        source_availability_client=source_availability_client,
        content_classification_client=content_classification_client,
        atomic_claim_client=atomic_claim_client,
        requirement_language_client=requirement_language_client,
        hypothesis_review_client=hypothesis_review_client,
        deterministic_repair_enabled=cfg.deterministic_repair_enabled and not args.disable_deterministic_repair,
        fallback_to_primary_repair=cfg.fallback_to_primary_repair and not args.no_primary_repair_fallback,
        fast_intake_enabled=intake_enabled,
        fast_intake_mode=args.fast_intake_mode or cfg.fast_intake_mode,
        fast_atomic_claim_enabled=atomic_enabled,
        fast_requirement_language_enabled=requirement_language_enabled,
        fast_hypothesis_review_enabled=hypothesis_review_enabled,
        fast_final_review_enabled=review_enabled,
        primary_large_case_max_tokens=cfg.primary_large_case_max_tokens,
        primary_large_case_requirement_threshold=cfg.primary_large_case_requirement_threshold,
        primary_phase_a_chunk_size=cfg.primary_phase_a_chunk_size,
        semantic_preparation_client=semantic_preparation_client,
        semantic_preparation_enabled=semantic_preparation_enabled,
        semantic_arbitration_client=client,
        semantic_arbitration_enabled=cfg.semantic_arbitration_enabled and not args.disable_semantic_arbitration,
        rca_synthesis_enabled=cfg.rca_synthesis_enabled and not args.disable_rca_synthesis,
    )
    raw = args.case.read_text(encoding="utf-8")
    result = pipeline.run(raw, progress=lambda s, d: print(f"[{s}] {d}", flush=True))
    args.output.write_text(result.final_report, encoding="utf-8")
    print(f"\nSaved: {args.output.resolve()}")
    for i, st in enumerate(result.stats, 1):
        print(f"Call {i}: {st.elapsed_seconds/60:.1f} min, model={st.model}, prompt={st.prompt_tokens}, completion={st.completion_tokens}, reasoning={st.reasoning_tokens}")
    if result.repair_log:
        print("Repair routing:")
        for e in result.repair_log:
            print(f"  pass={e.pass_index} route={e.route.value} outcome={e.outcome} model={e.model or '-'} elapsed={e.elapsed_seconds:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
