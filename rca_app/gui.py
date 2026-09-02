from __future__ import annotations

import html
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
    QSpinBox,
)

from . import __version__
from .cancellation import AnalysisCancelled, CancellationToken
from .config import AppConfig
from .lmstudio_client import LMStudioClient, LMStudioError
from .pipeline import RCAPipeline, PipelineValidationError
from .test_bundle import (
    builtin_regression_expectations,
    evaluate_semantic_acceptance,
    load_expected_results_manifest,
    load_test_bundle_zip,
    safe_case_alias,
    safe_filename_component,
)


DARK_STYLE = """
QMainWindow { background: #111418; }
QWidget { color: #e8edf2; font-size: 10pt; }
QGroupBox { border: 1px solid #303943; border-radius: 8px; margin-top: 10px; padding: 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #181d23; border: 1px solid #303943; border-radius: 6px; padding: 6px; selection-background-color: #3a6ea5;
}
QPushButton { background: #26313d; border: 1px solid #3a4857; border-radius: 6px; padding: 7px 12px; }
QPushButton:hover { background: #314152; }
QPushButton:disabled { color: #7f8993; background: #1b2127; }
QPushButton#stopButton { background: #8f2f36; border-color: #b94b54; color: #ffffff; font-weight: 700; }
QPushButton#stopButton:hover { background: #a83b44; }
QPushButton#stopButton:disabled { background: #352326; border-color: #543238; color: #8f7a7d; }
QTabWidget::pane { border: 1px solid #303943; border-radius: 6px; }
QTabBar::tab { background: #1b2127; padding: 8px 12px; margin-right: 2px; }
QTabBar::tab:selected { background: #2a3541; }
QProgressBar { border: 1px solid #303943; border-radius: 5px; text-align: center; background: #181d23; }
QProgressBar::chunk { background: #487aa8; border-radius: 4px; }
"""

LIGHT_STYLE = """
QMainWindow { background: #f4f7fb; }
QWidget { color: #1f2933; font-size: 10pt; }
QGroupBox { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; margin-top: 10px; padding: 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; background: #f4f7fb; }
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff; color: #17202a; border: 1px solid #c7d2df; border-radius: 6px; padding: 6px; selection-background-color: #b8d7f4;
}
QPushButton { background: #e8f1fb; color: #17324d; border: 1px solid #a9bfd6; border-radius: 6px; padding: 7px 12px; }
QPushButton:hover { background: #dbeaf8; }
QPushButton:pressed { background: #cbdff2; }
QPushButton:disabled { color: #94a3b8; background: #eef2f6; border-color: #d9e1e8; }
QPushButton#stopButton { background: #b53a43; color: #ffffff; border-color: #9d3038; font-weight: 700; }
QPushButton#stopButton:hover { background: #c64851; }
QPushButton#stopButton:disabled { background: #ead8da; color: #a68a8d; border-color: #d6bfc2; }
QCheckBox { spacing: 6px; }
QTabWidget::pane { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; }
QTabBar::tab { background: #e9eef5; color: #334155; padding: 8px 12px; margin-right: 2px; border: 1px solid #d6dee8; border-bottom: none; }
QTabBar::tab:selected { background: #ffffff; color: #0f3b66; }
QProgressBar { border: 1px solid #c7d2df; border-radius: 5px; text-align: center; background: #ffffff; color: #1f2933; }
QProgressBar::chunk { background: #4f8fc9; border-radius: 4px; }
"""


def _build_pipeline(config: AppConfig, cancellation_token: Optional[CancellationToken] = None) -> RCAPipeline:
    client = LMStudioClient(
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
        reasoning_effort=config.reasoning_effort,
        max_tokens=config.max_tokens,
        timeout_seconds=config.request_timeout_seconds,
        api_token=os.environ.get("LM_API_TOKEN", ""),
        cancellation_token=cancellation_token,
    )

    def make_fast(
        max_tokens: int,
        reasoning_effort: Optional[str] = None,
        thinking_mode: Optional[str] = None,
        transport: Optional[str] = None,
    ):
        if not config.fast_repair_model.strip():
            return None
        return LMStudioClient(
            base_url=config.base_url,
            model=config.fast_repair_model.strip(),
            temperature=config.fast_repair_temperature,
            reasoning_effort=reasoning_effort or config.fast_repair_reasoning_effort,
            max_tokens=max_tokens,
            timeout_seconds=config.request_timeout_seconds,
            api_token=os.environ.get("LM_API_TOKEN", ""),
            thinking_mode=thinking_mode or config.fast_repair_thinking_mode,
            transport=transport or config.fast_repair_transport,
            cancellation_token=cancellation_token,
        )

    repair_client = make_fast(config.fast_repair_max_tokens) if config.fast_repair_enabled else None
    intake_client = make_fast(config.fast_intake_max_tokens) if config.fast_intake_enabled else None
    source_availability_client = make_fast(config.fast_source_availability_max_tokens) if config.fast_intake_enabled else None
    content_classification_client = make_fast(config.fast_content_classification_max_tokens) if config.fast_intake_enabled else None
    atomic_claim_client = make_fast(config.fast_atomic_claim_max_tokens) if config.fast_atomic_claim_enabled else None
    requirement_language_client = make_fast(config.fast_requirement_language_max_tokens) if config.fast_requirement_language_enabled else None
    semantic_preparation_client = (
        make_fast(config.semantic_preparation_max_tokens)
        if config.semantic_preparation_enabled else None
    )
    if config.semantic_preparation_enabled and semantic_preparation_client is None:
        # Correctness fallback: use the primary model for semantic compilation
        # rather than letting Python interpret free-form requirement language.
        semantic_preparation_client = client
    hypothesis_review_client = make_fast(config.fast_hypothesis_review_max_tokens) if config.fast_hypothesis_review_enabled else None
    final_review_client = (
        make_fast(
            config.fast_final_review_max_tokens,
            reasoning_effort=config.fast_final_review_reasoning_effort,
            thinking_mode=config.fast_final_review_thinking_mode,
            transport=config.fast_final_review_transport,
        )
        if config.fast_final_review_enabled else None
    )

    return RCAPipeline(
        client,
        max_repair_passes=config.max_repair_passes,
        repair_client=repair_client,
        intake_client=intake_client,
        final_review_client=final_review_client,
        source_availability_client=source_availability_client,
        content_classification_client=content_classification_client,
        atomic_claim_client=atomic_claim_client,
        requirement_language_client=requirement_language_client,
        hypothesis_review_client=hypothesis_review_client,
        deterministic_repair_enabled=config.deterministic_repair_enabled,
        fallback_to_primary_repair=config.fallback_to_primary_repair,
        fast_intake_enabled=config.fast_intake_enabled,
        fast_intake_mode=config.fast_intake_mode,
        fast_atomic_claim_enabled=config.fast_atomic_claim_enabled,
        fast_requirement_language_enabled=config.fast_requirement_language_enabled,
        fast_hypothesis_review_enabled=config.fast_hypothesis_review_enabled,
        fast_final_review_enabled=config.fast_final_review_enabled,
        primary_large_case_max_tokens=config.primary_large_case_max_tokens,
        primary_large_case_requirement_threshold=config.primary_large_case_requirement_threshold,
        primary_phase_a_chunk_size=config.primary_phase_a_chunk_size,
        semantic_preparation_client=semantic_preparation_client,
        semantic_preparation_enabled=config.semantic_preparation_enabled,
        semantic_arbitration_client=client,
        semantic_arbitration_enabled=config.semantic_arbitration_enabled,
        rca_synthesis_enabled=config.rca_synthesis_enabled,
        cancellation_token=cancellation_token,
    )


class AnalysisWorker(QObject):
    progress = Signal(str, str)
    trace = Signal(object)
    finished = Signal(object)
    failed = Signal(str, object, object, object, object, object)
    cancelled = Signal(str)

    def __init__(self, config: AppConfig, raw_case: str):
        super().__init__()
        self.config = config
        self.raw_case = raw_case
        self.cancellation_token = CancellationToken()
        self.pipeline = None

    def request_cancel(self):
        reason = "Stopped by user from the RCA Analyst GUI."
        self.cancellation_token.cancel(reason)
        if self.pipeline is not None:
            self.pipeline.cancel(reason)

    @Slot()
    def run(self):
        try:
            self.pipeline = _build_pipeline(self.config, self.cancellation_token)
            result = self.pipeline.run(
                self.raw_case,
                progress=lambda a, b: self.progress.emit(a, b),
                trace=lambda event: self.trace.emit(event),
            )
            self.finished.emit(result)
        except AnalysisCancelled as exc:
            self.cancelled.emit(str(exc))
        except PipelineValidationError as exc:
            self.failed.emit(str(exc), exc.validated, exc.canonical_case, exc.attempts, exc.stats, exc.repair_log)
        except Exception as exc:
            self.failed.emit(str(exc), None, None, [], [], [])


class BatchAnalysisWorker(QObject):
    """Run bundled regression cases strictly one after another in one worker thread."""

    progress = Signal(str, str, str)
    trace = Signal(str, object)
    case_started = Signal(str, int, int)
    case_finished = Signal(str, object)
    case_failed = Signal(str, str, object, object, object, object, object)
    finished = Signal(object)
    cancelled = Signal(str, object)

    def __init__(self, config: AppConfig, cases):
        super().__init__()
        self.config = config
        self.cases = list(cases)
        self.cancellation_token = CancellationToken()
        self.pipeline = None

    def request_cancel(self):
        reason = "Stopped by user from the RCA Analyst GUI."
        self.cancellation_token.cancel(reason)
        if self.pipeline is not None:
            self.pipeline.cancel(reason)

    @Slot()
    def run(self):
        summary = []
        total = len(self.cases)
        for index, (case_id, raw_case) in enumerate(self.cases, start=1):
            if self.cancellation_token.cancelled:
                break
            self.case_started.emit(case_id, index, total)
            try:
                # A fresh pipeline object per case guarantees a fresh analysis
                # context while still executing sequentially in this one thread.
                self.pipeline = _build_pipeline(self.config, self.cancellation_token)
                result = self.pipeline.run(
                    raw_case,
                    progress=lambda stage, detail, cid=case_id: self.progress.emit(cid, stage, detail),
                    trace=lambda event, cid=case_id: self.trace.emit(cid, event),
                )
                summary.append({"case": case_id, "status": "PASS"})
                self.case_finished.emit(case_id, result)
            except AnalysisCancelled as exc:
                summary.append({"case": case_id, "status": "ABORTED", "message": str(exc)})
                self.cancelled.emit(str(exc), summary)
                return
            except PipelineValidationError as exc:
                summary.append({"case": case_id, "status": "FAILED", "message": str(exc)})
                self.case_failed.emit(
                    case_id, str(exc), exc.validated, exc.canonical_case, exc.attempts, exc.stats, exc.repair_log
                )
            except Exception as exc:
                summary.append({"case": case_id, "status": "FAILED", "message": str(exc)})
                self.case_failed.emit(case_id, str(exc), None, None, [], [], [])
        self.finished.emit(summary)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"RCA Analyst POC v{__version__} — Multi-Model Evidence-Safe RCA")
        self.resize(1500, 900)
        self.config = AppConfig.load()
        self.current_result = None
        self.failure_diagnostics = None
        self.worker_thread: Optional[QThread] = None
        self._worker = None
        self.batch_active = False
        self.batch_output_dir: Optional[Path] = None
        self.batch_records = []
        self.batch_label = "Sequential Batch"
        self.batch_summary_stem = f"batch_summary_v{__version__}"
        self.batch_bundle_source = ""
        self.batch_expected_total = 0
        self._batch_source_files = {}
        self._batch_expectations = {}
        self._pipeline_trace_events = {}
        self._pipeline_trace_case = ""
        self._build_ui()
        self._load_config_into_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        connection = QGroupBox("LM Studio API")
        conn_layout = QHBoxLayout(connection)
        self.base_url = QLineEdit()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.refresh_btn = QPushButton("Refresh Models")
        self.test_btn = QPushButton("Test Connection")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        conn_layout.addWidget(QLabel("Base URL"))
        conn_layout.addWidget(self.base_url, 2)
        conn_layout.addWidget(QLabel("Model"))
        conn_layout.addWidget(self.model_combo, 3)
        conn_layout.addWidget(self.refresh_btn)
        conn_layout.addWidget(self.test_btn)
        conn_layout.addWidget(QLabel("Theme"))
        conn_layout.addWidget(self.theme_combo)
        outer.addWidget(connection)

        settings = QGroupBox("Inference / Pipeline Settings")
        set_layout = QHBoxLayout(settings)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0.0, 2.0)
        self.temp.setSingleStep(0.05)
        self.temp.setDecimals(2)
        self.reasoning = QComboBox()
        self.reasoning.addItem("Provider default", "provider_default")
        self.reasoning.addItem("Low", "low")
        self.reasoning.addItem("Medium", "medium")
        self.reasoning.addItem("Extra High", "xhigh")
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(512, 65536)
        self.max_tokens.setSingleStep(512)
        self.repairs = QSpinBox()
        self.repairs.setRange(0, 3)
        self.large_case_tokens = QSpinBox()
        self.large_case_tokens.setRange(4096, 65536)
        self.large_case_tokens.setSingleStep(1024)
        self.large_case_threshold = QSpinBox()
        self.large_case_threshold.setRange(2, 50)
        self.phase_a_chunk_size = QSpinBox()
        self.phase_a_chunk_size.setRange(1, 20)
        set_layout.addWidget(QLabel("Primary temperature"))
        set_layout.addWidget(self.temp)
        set_layout.addWidget(QLabel("Primary reasoning"))
        set_layout.addWidget(self.reasoning)
        set_layout.addWidget(QLabel("Primary output tokens"))
        set_layout.addWidget(self.max_tokens)
        set_layout.addStretch(1)
        # Legacy v0.7 Phase-A/repair controls are kept as hidden config fields so
        # old saved settings remain loadable, but they are not part of the v0.8
        # production topology and must not appear as active tuning knobs.
        for legacy_widget in (self.large_case_tokens, self.large_case_threshold, self.phase_a_chunk_size, self.repairs):
            legacy_widget.setVisible(False)
        outer.addWidget(settings)

        repair_settings = QGroupBox(f"Multi-Model Architecture v{__version__} — semantic compiler + deterministic compliance + adaptive 27B")
        repair_layout = QVBoxLayout(repair_settings)
        fast_row1 = QHBoxLayout()
        fast_row2 = QHBoxLayout()

        self.deterministic_repair = QCheckBox("Prefer deterministic repair")
        self.fast_intake_enabled = QCheckBox("4B intake")
        self.fast_intake_enabled.setToolTip(
            "Use Qwen3.5-4B to understand inconsistent natural-language testcase structure and source availability. "
            "Python still owns canonical evidence IDs and trace mechanics."
        )
        self.fast_intake_mode = QComboBox()
        self.fast_intake_mode.addItem("Auto", "auto")
        self.fast_intake_mode.addItem("Always", "always")
        self.fast_intake_mode.addItem("Off", "off")
        self.fast_repair_enabled = QCheckBox("4B field repair")
        self.fast_final_review_enabled = QCheckBox("4B wording audit")
        self.fast_model_combo = QComboBox()
        self.fast_model_combo.setEditable(True)
        self.fast_reasoning = QComboBox()
        self.fast_reasoning.addItem("Provider default", "provider_default")
        self.fast_reasoning.addItem("Low", "low")
        self.fast_reasoning.addItem("Medium", "medium")
        self.fast_thinking = QComboBox()
        self.fast_thinking.addItem("Off", "off")
        self.fast_thinking.addItem("Provider default", "provider_default")
        self.fast_thinking.setToolTip(
            "Applies to v0.8 semantic preparation and narrow 4B services. Requirement/evidence language is compiled here; Python executes only verified structured semantics."
        )
        self.fast_transport = QComboBox()
        self.fast_transport.addItem("Auto", "auto")
        self.fast_transport.addItem("OpenAI chat", "openai-chat")
        self.fast_transport.addItem("Qwen3.5 manual", "qwen35-manual")
        self.fast_max_tokens = QSpinBox()
        self.fast_max_tokens.setRange(256, 8192)
        self.fast_max_tokens.setSingleStep(256)
        self.fast_intake_max_tokens = QSpinBox()
        self.fast_intake_max_tokens.setRange(512, 8192)
        self.fast_intake_max_tokens.setSingleStep(256)
        self.fast_final_review_max_tokens = QSpinBox()
        self.fast_final_review_max_tokens.setRange(256, 4096)
        self.fast_final_review_max_tokens.setSingleStep(128)
        self.fast_final_review_reasoning = QComboBox()
        self.fast_final_review_reasoning.addItem("Provider default", "provider_default")
        self.fast_final_review_reasoning.addItem("Low", "low")
        self.fast_final_review_reasoning.addItem("Medium", "medium")
        self.fast_final_review_thinking = QComboBox()
        self.fast_final_review_thinking.addItem("Provider default / ON", "provider_default")
        self.fast_final_review_thinking.addItem("Off", "off")
        self.fast_final_review_transport = QComboBox()
        self.fast_final_review_transport.addItem("OpenAI chat", "openai-chat")
        self.fast_final_review_transport.addItem("Auto", "auto")
        self.fast_final_review_transport.addItem("Qwen3.5 manual (non-thinking)", "qwen35-manual")
        self.fast_atomic_claim_enabled = QCheckBox("4B atomic claims")
        self.fast_requirement_language_enabled = QCheckBox("4B requirement language")
        self.fast_hypothesis_review_enabled = QCheckBox("4B hypothesis review")
        self.semantic_preparation_enabled = QCheckBox("4B semantic preparation")
        self.semantic_preparation_enabled.setToolTip("Mandatory v0.8 language compiler: free-form requirements -> Requirement IR and contextual evidence annotations in one case-level call. If no 4B model is configured, the primary model is used for correctness.")
        self.semantic_arbitration_enabled = QCheckBox("27B semantic arbitration")
        self.semantic_arbitration_enabled.setToolTip("At most one case-level 27B call when material semantic ambiguity remains after fast preparation.")
        self.rca_synthesis_enabled = QCheckBox("27B RCA when justified")
        self.rca_synthesis_enabled.setToolTip("Run deep RCA only when mechanism-oriented evidence exists; a bare compliance violation does not trigger it.")
        self.semantic_preparation_tokens = QSpinBox()
        self.semantic_preparation_tokens.setRange(1024, 16000)
        self.semantic_preparation_tokens.setSingleStep(512)
        self.fast_source_availability_tokens = QSpinBox()
        self.fast_source_availability_tokens.setRange(256, 4096)
        self.fast_content_classification_tokens = QSpinBox()
        self.fast_content_classification_tokens.setRange(512, 8192)
        self.fast_atomic_claim_tokens = QSpinBox()
        self.fast_atomic_claim_tokens.setRange(512, 8192)
        self.fast_requirement_language_tokens = QSpinBox()
        self.fast_requirement_language_tokens.setRange(512, 8192)
        self.fast_hypothesis_review_tokens = QSpinBox()
        self.fast_hypothesis_review_tokens.setRange(256, 4096)
        self.fast_final_review_thinking.setToolTip(
            "v0.8 wording audit has zero semantic authority. It cannot change applicability, sufficiency, timing or compliance verdicts."
        )
        self.primary_fallback = QCheckBox("Primary fallback after failed 4B repair")

        fast_row1.addWidget(self.fast_intake_enabled)
        fast_row1.addWidget(QLabel("Routing"))
        fast_row1.addWidget(self.fast_intake_mode)
        fast_row1.addSpacing(12)
        fast_row1.addWidget(self.fast_final_review_enabled)
        fast_row1.addWidget(QLabel("Review tokens"))
        fast_row1.addWidget(self.fast_final_review_max_tokens)
        fast_row1.addStretch(1)

        fast_row2.addWidget(QLabel("4B model"))
        fast_row2.addWidget(self.fast_model_combo, 3)
        fast_row2.addWidget(QLabel("Reasoning"))
        fast_row2.addWidget(self.fast_reasoning)
        fast_row2.addWidget(QLabel("Thinking"))
        fast_row2.addWidget(self.fast_thinking)
        fast_row2.addWidget(QLabel("Transport"))
        fast_row2.addWidget(self.fast_transport)
        # v0.7 field-repair controls remain instantiated only for config migration.
        for legacy_widget in (self.fast_repair_enabled, self.fast_max_tokens, self.deterministic_repair, self.primary_fallback, self.fast_intake_max_tokens, self.fast_atomic_claim_enabled, self.fast_requirement_language_enabled, self.fast_atomic_claim_tokens, self.fast_requirement_language_tokens):
            legacy_widget.setVisible(False)

        fast_row3 = QHBoxLayout()
        fast_row3.addWidget(QLabel("Final review reasoning"))
        fast_row3.addWidget(self.fast_final_review_reasoning)
        fast_row3.addWidget(QLabel("Final review thinking"))
        fast_row3.addWidget(self.fast_final_review_thinking)
        fast_row3.addWidget(QLabel("Final review transport"))
        fast_row3.addWidget(self.fast_final_review_transport)
        fast_row3.addStretch(1)

        fast_row4 = QHBoxLayout()
        fast_row4.addWidget(QLabel("Availability tokens"))
        fast_row4.addWidget(self.fast_source_availability_tokens)
        fast_row4.addWidget(QLabel("Content tokens"))
        fast_row4.addWidget(self.fast_content_classification_tokens)
        fast_row4.addSpacing(12)
        fast_row4.addWidget(self.semantic_preparation_enabled)
        fast_row4.addWidget(QLabel("Semantic tokens"))
        fast_row4.addWidget(self.semantic_preparation_tokens)
        fast_row4.addWidget(self.semantic_arbitration_enabled)
        fast_row4.addWidget(self.rca_synthesis_enabled)
        fast_row4.addWidget(self.fast_hypothesis_review_enabled)
        fast_row4.addWidget(self.fast_hypothesis_review_tokens)
        fast_row4.addStretch(1)

        repair_layout.addLayout(fast_row1)
        repair_layout.addLayout(fast_row2)
        repair_layout.addLayout(fast_row3)
        repair_layout.addLayout(fast_row4)
        outer.addWidget(repair_settings)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)

        # Chat-like case console.
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setPlaceholderText("Cases and completed analyses appear here.")
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText("Paste the complete current test case here: ticket, test steps/result, requirements, history, diagnostics, traces, etc.")
        self.composer.setMinimumHeight(250)
        button_row = QHBoxLayout()
        self.load_example_btn = QPushButton("Load TEST-001")
        self.load_test2_btn = QPushButton("Load TEST-002")
        self.load_test3_btn = QPushButton("Load TEST-003")
        self.run_all_tests_btn = QPushButton("Run TEST-001 → TEST-003")
        self.run_all_tests_btn.setToolTip("Run the three built-in regression cases sequentially (never in parallel) and auto-save every report/session.")
        self.run_bundle_btn = QPushButton("Run Test Bundle…")
        self.run_bundle_btn.setToolTip("Select a ZIP containing .txt test cases. Every case is executed strictly sequentially with a fresh pipeline/context.")
        self.analyze_btn = QPushButton("Analyze Case")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setToolTip("Abort the active single-case or sequential-batch pipeline run.")
        self.stop_btn.setEnabled(False)
        self.clear_btn = QPushButton("New / Clear")
        button_row.addWidget(self.load_example_btn)
        button_row.addWidget(self.load_test2_btn)
        button_row.addWidget(self.load_test3_btn)
        button_row.addWidget(self.run_all_tests_btn)
        button_row.addWidget(self.run_bundle_btn)
        button_row.addStretch(1)
        button_row.addWidget(self.clear_btn)
        button_row.addWidget(self.stop_btn)
        button_row.addWidget(self.analyze_btn)
        left_layout.addWidget(QLabel("Case Chat"))
        left_layout.addWidget(self.transcript, 2)
        left_layout.addWidget(self.composer, 1)
        left_layout.addLayout(button_row)
        splitter.addWidget(left)

        # Pipeline inspection/result pane.
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.report_view = QTextBrowser()
        self.pipeline_view = QPlainTextEdit()
        self.pipeline_view.setReadOnly(True)
        self.batch_view = QPlainTextEdit()
        self.batch_view.setReadOnly(True)
        self.validation_view = QPlainTextEdit()
        self.validation_view.setReadOnly(True)
        self.canonical_view = QPlainTextEdit()
        self.canonical_view.setReadOnly(True)
        self.json_view = QPlainTextEdit()
        self.json_view.setReadOnly(True)
        self.stats_view = QPlainTextEdit()
        self.stats_view.setReadOnly(True)
        self.attempts_view = QPlainTextEdit()
        self.attempts_view.setReadOnly(True)
        self.repair_view = QPlainTextEdit()
        self.repair_view.setReadOnly(True)

        # User-friendly live pipeline inspector. The left side is a stage map;
        # the right side explains the selected stage and exposes its exact input
        # and output without forcing raw JSON into the primary view.
        self.live_pipeline_tab = QWidget()
        live_layout = QVBoxLayout(self.live_pipeline_tab)
        live_layout.setContentsMargins(6, 6, 6, 6)
        live_header = QHBoxLayout()
        self.live_pipeline_case_label = QLabel("No active analysis")
        self.live_pipeline_follow = QCheckBox("Follow active stage")
        self.live_pipeline_follow.setChecked(True)
        live_header.addWidget(self.live_pipeline_case_label, 1)
        live_header.addWidget(self.live_pipeline_follow)
        live_layout.addLayout(live_header)
        live_splitter = QSplitter(Qt.Horizontal)
        self.live_stage_list = QListWidget()
        self.live_stage_list.setMinimumWidth(270)
        live_splitter.addWidget(self.live_stage_list)
        live_detail = QWidget()
        live_detail_layout = QVBoxLayout(live_detail)
        live_detail_layout.setContentsMargins(4, 0, 0, 0)
        self.live_stage_summary = QTextBrowser()
        self.live_stage_summary.setMinimumHeight(120)
        self.live_stage_io_tabs = QTabWidget()
        self.live_stage_input = QPlainTextEdit()
        self.live_stage_input.setReadOnly(True)
        self.live_stage_output = QPlainTextEdit()
        self.live_stage_output.setReadOnly(True)
        self.live_stage_io_tabs.addTab(self.live_stage_input, "Stage Input")
        self.live_stage_io_tabs.addTab(self.live_stage_output, "Stage Output")
        live_detail_layout.addWidget(self.live_stage_summary)
        live_detail_layout.addWidget(self.live_stage_io_tabs, 1)
        live_splitter.addWidget(live_detail)
        live_splitter.setSizes([300, 900])
        live_layout.addWidget(live_splitter, 1)

        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.pipeline_view.setFont(mono)
        self.batch_view.setFont(mono)
        self.validation_view.setFont(mono)
        self.canonical_view.setFont(mono)
        self.json_view.setFont(mono)
        self.stats_view.setFont(mono)
        self.attempts_view.setFont(mono)
        self.repair_view.setFont(mono)
        self.live_stage_input.setFont(mono)
        self.live_stage_output.setFont(mono)
        self.tabs.addTab(self.report_view, "Final Report")
        self.tabs.addTab(self.live_pipeline_tab, "Live Pipeline")
        self.tabs.addTab(self.pipeline_view, "Stage Log")
        self.tabs.addTab(self.batch_view, "Sequential Batch")
        self.tabs.addTab(self.validation_view, "Validation")
        self.tabs.addTab(self.canonical_view, "Canonical Input")
        self.tabs.addTab(self.json_view, "Structured JSON")
        self.tabs.addTab(self.stats_view, "API Stats")
        self.tabs.addTab(self.attempts_view, "LLM Attempts")
        self.tabs.addTab(self.repair_view, "Repair Routing")
        export_row = QHBoxLayout()
        self.export_md_btn = QPushButton("Export Report .md")
        self.export_json_btn = QPushButton("Export Session .json")
        self.export_md_btn.setEnabled(False)
        self.export_json_btn.setEnabled(False)
        export_row.addStretch(1)
        export_row.addWidget(self.export_md_btn)
        export_row.addWidget(self.export_json_btn)
        right_layout.addWidget(self.tabs)
        right_layout.addLayout(export_row)
        splitter.addWidget(right)
        splitter.setSizes([650, 850])

        footer = QHBoxLayout()
        self.stage_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        footer.addWidget(self.stage_label)
        footer.addWidget(self.progress, 1)
        outer.addLayout(footer)

        self.refresh_btn.clicked.connect(self.refresh_models)
        self.test_btn.clicked.connect(self.test_connection)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.analyze_btn.clicked.connect(self.analyze_case)
        self.stop_btn.clicked.connect(self.stop_analysis)
        self.run_all_tests_btn.clicked.connect(self.run_all_tests)
        self.run_bundle_btn.clicked.connect(self.run_test_bundle)
        self.clear_btn.clicked.connect(self.clear_case)
        self.load_example_btn.clicked.connect(self.load_example)
        self.load_test2_btn.clicked.connect(self.load_test2)
        self.load_test3_btn.clicked.connect(self.load_test3)
        self.export_md_btn.clicked.connect(self.export_report)
        self.export_json_btn.clicked.connect(self.export_session)
        self.live_stage_list.currentRowChanged.connect(self._on_live_stage_selected)

    def _load_config_into_ui(self):
        self.base_url.setText(self.config.base_url)
        self.model_combo.setEditText(self.config.model)
        idx = self.theme_combo.findData(self.config.theme if self.config.theme in {"dark", "light"} else "dark")
        self.theme_combo.setCurrentIndex(max(0, idx))
        self._apply_theme(str(self.theme_combo.currentData()))
        self.temp.setValue(self.config.temperature)
        idx = self.reasoning.findData(self.config.reasoning_effort)
        self.reasoning.setCurrentIndex(max(0, idx))
        self.max_tokens.setValue(self.config.max_tokens)
        self.large_case_tokens.setValue(self.config.primary_large_case_max_tokens)
        self.large_case_threshold.setValue(self.config.primary_large_case_requirement_threshold)
        self.phase_a_chunk_size.setValue(self.config.primary_phase_a_chunk_size)
        self.repairs.setValue(self.config.max_repair_passes)
        self.deterministic_repair.setChecked(self.config.deterministic_repair_enabled)
        self.fast_intake_enabled.setChecked(self.config.fast_intake_enabled)
        idx = self.fast_intake_mode.findData(self.config.fast_intake_mode)
        self.fast_intake_mode.setCurrentIndex(max(0, idx))
        self.fast_repair_enabled.setChecked(self.config.fast_repair_enabled)
        self.semantic_preparation_enabled.setChecked(self.config.semantic_preparation_enabled)
        self.semantic_arbitration_enabled.setChecked(self.config.semantic_arbitration_enabled)
        self.rca_synthesis_enabled.setChecked(self.config.rca_synthesis_enabled)
        self.semantic_preparation_tokens.setValue(self.config.semantic_preparation_max_tokens)
        self.fast_atomic_claim_enabled.setChecked(self.config.fast_atomic_claim_enabled)
        self.fast_requirement_language_enabled.setChecked(self.config.fast_requirement_language_enabled)
        self.fast_hypothesis_review_enabled.setChecked(self.config.fast_hypothesis_review_enabled)
        self.fast_final_review_enabled.setChecked(self.config.fast_final_review_enabled)
        self.fast_model_combo.setEditText(self.config.fast_repair_model)
        idx = self.fast_reasoning.findData(self.config.fast_repair_reasoning_effort)
        self.fast_reasoning.setCurrentIndex(max(0, idx))
        idx = self.fast_thinking.findData(self.config.fast_repair_thinking_mode)
        self.fast_thinking.setCurrentIndex(max(0, idx))
        idx = self.fast_transport.findData(self.config.fast_repair_transport)
        self.fast_transport.setCurrentIndex(max(0, idx))
        self.fast_intake_max_tokens.setValue(self.config.fast_intake_max_tokens)
        self.fast_source_availability_tokens.setValue(self.config.fast_source_availability_max_tokens)
        self.fast_content_classification_tokens.setValue(self.config.fast_content_classification_max_tokens)
        self.fast_atomic_claim_tokens.setValue(self.config.fast_atomic_claim_max_tokens)
        self.fast_requirement_language_tokens.setValue(self.config.fast_requirement_language_max_tokens)
        self.fast_hypothesis_review_tokens.setValue(self.config.fast_hypothesis_review_max_tokens)
        self.fast_max_tokens.setValue(self.config.fast_repair_max_tokens)
        self.fast_final_review_max_tokens.setValue(self.config.fast_final_review_max_tokens)
        idx = self.fast_final_review_reasoning.findData(self.config.fast_final_review_reasoning_effort)
        self.fast_final_review_reasoning.setCurrentIndex(max(0, idx))
        idx = self.fast_final_review_thinking.findData(self.config.fast_final_review_thinking_mode)
        self.fast_final_review_thinking.setCurrentIndex(max(0, idx))
        idx = self.fast_final_review_transport.findData(self.config.fast_final_review_transport)
        self.fast_final_review_transport.setCurrentIndex(max(0, idx))
        self.primary_fallback.setChecked(self.config.fallback_to_primary_repair)

    def _collect_config(self) -> AppConfig:
        cfg = AppConfig(
            base_url=self.base_url.text().strip(),
            model=self.model_combo.currentText().strip(),
            temperature=float(self.temp.value()),
            reasoning_effort=str(self.reasoning.currentData()),
            max_tokens=int(self.max_tokens.value()),
            primary_large_case_max_tokens=int(self.large_case_tokens.value()),
            primary_large_case_requirement_threshold=int(self.large_case_threshold.value()),
            primary_phase_a_chunk_size=int(self.phase_a_chunk_size.value()),
            max_repair_passes=int(self.repairs.value()),
            request_timeout_seconds=self.config.request_timeout_seconds,
            semantic_preparation_enabled=self.semantic_preparation_enabled.isChecked(),
            semantic_preparation_max_tokens=int(self.semantic_preparation_tokens.value()),
            semantic_arbitration_enabled=self.semantic_arbitration_enabled.isChecked(),
            rca_synthesis_enabled=self.rca_synthesis_enabled.isChecked(),
            deterministic_repair_enabled=self.deterministic_repair.isChecked(),
            fast_intake_enabled=self.fast_intake_enabled.isChecked(),
            fast_intake_mode=str(self.fast_intake_mode.currentData() or "auto"),
            fast_intake_max_tokens=int(self.fast_intake_max_tokens.value()),
            fast_source_availability_max_tokens=int(self.fast_source_availability_tokens.value()),
            fast_content_classification_max_tokens=int(self.fast_content_classification_tokens.value()),
            fast_atomic_claim_enabled=self.fast_atomic_claim_enabled.isChecked(),
            fast_atomic_claim_max_tokens=int(self.fast_atomic_claim_tokens.value()),
            fast_requirement_language_enabled=self.fast_requirement_language_enabled.isChecked(),
            fast_requirement_language_max_tokens=int(self.fast_requirement_language_tokens.value()),
            fast_repair_enabled=self.fast_repair_enabled.isChecked(),
            fast_hypothesis_review_enabled=self.fast_hypothesis_review_enabled.isChecked(),
            fast_hypothesis_review_max_tokens=int(self.fast_hypothesis_review_tokens.value()),
            fast_final_review_enabled=self.fast_final_review_enabled.isChecked(),
            fast_final_review_max_tokens=int(self.fast_final_review_max_tokens.value()),
            fast_final_review_reasoning_effort=str(self.fast_final_review_reasoning.currentData()),
            fast_final_review_thinking_mode=str(self.fast_final_review_thinking.currentData()),
            fast_final_review_transport=str(self.fast_final_review_transport.currentData()),
            fast_repair_model=self.fast_model_combo.currentText().strip(),
            fast_repair_temperature=self.config.fast_repair_temperature,
            fast_repair_reasoning_effort=str(self.fast_reasoning.currentData()),
            fast_repair_thinking_mode=str(self.fast_thinking.currentData()),
            fast_repair_transport=str(self.fast_transport.currentData()),
            fast_repair_max_tokens=int(self.fast_max_tokens.value()),
            fallback_to_primary_repair=self.primary_fallback.isChecked(),
            theme=str(self.theme_combo.currentData() or "dark"),
        )
        cfg.save()
        self.config = cfg
        return cfg

    def _apply_theme(self, theme: str):
        theme = "light" if theme == "light" else "dark"
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(LIGHT_STYLE if theme == "light" else DARK_STYLE)
        # QTextBrowser document backgrounds are styled separately through HTML,
        # so refresh transcript colors on the next appended message.

    @Slot(int)
    def _on_theme_changed(self, _index: int):
        theme = str(self.theme_combo.currentData() or "dark")
        self._apply_theme(theme)
        self.config.theme = theme
        self.config.save()

    @Slot()
    def refresh_models(self):
        try:
            cfg = self._collect_config()
            client = LMStudioClient(cfg.base_url, cfg.model or "unused")
            models = client.list_models()
            current = self.model_combo.currentText().strip()
            fast_current = self.fast_model_combo.currentText().strip()
            self.model_combo.clear()
            self.model_combo.addItems(models)
            self.fast_model_combo.clear()
            self.fast_model_combo.addItems(models)
            if current and self.model_combo.findText(current) < 0:
                self.model_combo.addItem(current)
            if fast_current and self.fast_model_combo.findText(fast_current) < 0:
                self.fast_model_combo.addItem(fast_current)
            if current:
                self.model_combo.setCurrentText(current)
            elif models:
                self.model_combo.setCurrentIndex(0)
            if fast_current:
                self.fast_model_combo.setCurrentText(fast_current)
            self.stage_label.setText(f"Found {len(models)} model(s)")
        except Exception as exc:
            QMessageBox.critical(self, "LM Studio", str(exc))

    @Slot()
    def test_connection(self):
        try:
            cfg = self._collect_config()
            client = LMStudioClient(cfg.base_url, cfg.model or "unused")
            ok, msg = client.test_connection()
            QMessageBox.information(self, "LM Studio", msg)
        except Exception as exc:
            QMessageBox.critical(self, "LM Studio", str(exc))

    @Slot()
    def analyze_case(self):
        raw = self.composer.toPlainText().strip()
        cfg = self._collect_config()
        if not raw:
            QMessageBox.warning(self, "RCA Analyst", "Paste a test case first.")
            return
        if not cfg.model:
            QMessageBox.warning(self, "RCA Analyst", "Select or enter the LM Studio model identifier first.")
            return
        if self.worker_thread and self.worker_thread.isRunning():
            return

        self.current_result = None
        self.failure_diagnostics = None
        self.report_view.clear()
        self.pipeline_view.clear()
        self.batch_view.clear()
        self.validation_view.clear()
        self.canonical_view.clear()
        self.json_view.clear()
        self.stats_view.clear()
        self.attempts_view.clear()
        self.repair_view.clear()
        self._reset_live_pipeline("Single case analysis")
        self.export_md_btn.setEnabled(False)
        self.export_json_btn.setEnabled(False)
        self._append_user_message(raw)
        self._set_busy(True)
        self.progress.setRange(0, 0)  # Indeterminate during a potentially long local generation.
        self.stage_label.setText("Starting...")

        self.worker_thread = QThread(self)
        worker = AnalysisWorker(cfg, raw)
        worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.trace.connect(self._on_trace_event)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(self.worker_thread.quit)
        worker.failed.connect(self.worker_thread.quit)
        worker.cancelled.connect(self.worker_thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        self.worker_thread.finished.connect(self._on_worker_thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()
        self._worker = worker

    @Slot()
    def run_all_tests(self):
        """Run TEST-001, TEST-002 and TEST-003 strictly sequentially."""
        cfg = self._collect_config()
        if not cfg.model:
            QMessageBox.warning(self, "RCA Analyst", "Select or enter the LM Studio model identifier first.")
            return
        if self.worker_thread and self.worker_thread.isRunning():
            return

        examples = Path(__file__).resolve().parent.parent / "examples"
        specs = [
            ("TEST-001", examples / "TEST-001.txt"),
            ("TEST-002", examples / "TEST-002.txt"),
            ("TEST-003", examples / "TEST-003.txt"),
        ]
        missing = [str(path) for _, path in specs if not path.exists()]
        if missing:
            QMessageBox.critical(self, "3-Case Batch", "Missing built-in test case(s):\n" + "\n".join(missing))
            return

        cases = [(case_id, path.read_text(encoding="utf-8")) for case_id, path in specs]
        source_files = {case_id: str(path) for case_id, path in specs}
        self._start_sequential_batch(
            cfg,
            cases,
            label="Built-in TEST-001 → TEST-003",
            source_files=source_files,
            expectations=builtin_regression_expectations(),
            summary_stem=f"TC1-TC3_batch_summary_v{__version__}",
            output_suffix="built_in_TC1_TC3",
        )

    @Slot()
    def run_test_bundle(self):
        """Select a ZIP bundle and run every .txt test case strictly sequentially."""
        cfg = self._collect_config()
        if not cfg.model:
            QMessageBox.warning(self, "RCA Analyst", "Select or enter the LM Studio model identifier first.")
            return
        if self.worker_thread and self.worker_thread.isRunning():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Test Case Bundle",
            "",
            "Test bundles (*.zip);;All files (*.*)",
        )
        if not path:
            return

        bundle_path = Path(path)
        try:
            bundle_cases = load_test_bundle_zip(bundle_path)
            expectations = load_expected_results_manifest(bundle_path)
        except ValueError as exc:
            QMessageBox.critical(self, "Test Bundle", str(exc))
            return

        cases = [(item.case_id, item.raw_text) for item in bundle_cases]
        source_files = {item.case_id: item.source_name for item in bundle_cases}
        bundle_name = bundle_path.stem
        self._start_sequential_batch(
            cfg,
            cases,
            label=f"Bundle: {bundle_name}",
            source_files=source_files,
            expectations=expectations,
            summary_stem=f"{safe_filename_component(bundle_name, 'bundle')}_batch_summary_v{__version__}",
            output_suffix=safe_filename_component(bundle_name, "bundle"),
            bundle_source=str(bundle_path),
        )

    def _start_sequential_batch(
        self,
        cfg: AppConfig,
        cases,
        *,
        label: str,
        source_files=None,
        expectations=None,
        summary_stem: str,
        output_suffix: str,
        bundle_source: str = "",
    ):
        if not cases:
            QMessageBox.warning(self, "Sequential Batch", "No test cases were found.")
            return

        self.batch_active = True
        self.batch_records = []
        self.batch_label = label
        self.batch_summary_stem = summary_stem
        self.batch_bundle_source = bundle_source
        self.batch_expected_total = len(cases)
        self._batch_source_files = dict(source_files or {})
        self._batch_expectations = dict(expectations or {})
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = safe_filename_component(output_suffix, "batch")
        self.batch_output_dir = Path(__file__).resolve().parent.parent / "batch_results" / f"{stamp}_{suffix}"
        self.batch_output_dir.mkdir(parents=True, exist_ok=True)
        self._batch_case_texts = {case_id: raw for case_id, raw in cases}

        self.current_result = None
        self.failure_diagnostics = None
        self.batch_view.clear()
        self.pipeline_view.clear()
        self.batch_view.appendPlainText(f"RCA Analyst POC v{__version__} sequential batch")
        self.batch_view.appendPlainText(f"Batch: {label}")
        self.batch_view.appendPlainText(f"Cases: {len(cases)}")
        self.batch_view.appendPlainText("Execution mode: SEQUENTIAL (one case at a time; no parallel LLM calls)")
        if bundle_source:
            self.batch_view.appendPlainText(f"Bundle source: {bundle_source}")
        self.batch_view.appendPlainText(f"Output directory: {self.batch_output_dir}")
        self.batch_view.appendPlainText("")
        for index, (case_id, _raw) in enumerate(cases, start=1):
            source = self._batch_source_files.get(case_id, "")
            suffix_text = f" | {source}" if source else ""
            self.batch_view.appendPlainText(f"Queued [{index}/{len(cases)}] {case_id}{suffix_text}")
        self.batch_view.appendPlainText("")
        self.tabs.setCurrentWidget(self.batch_view)
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.stage_label.setText(f"Starting sequential batch — 0/{len(cases)} complete")

        self.worker_thread = QThread(self)
        worker = BatchAnalysisWorker(cfg, cases)
        worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(worker.run)
        worker.case_started.connect(self._on_batch_case_started)
        worker.progress.connect(self._on_batch_progress)
        worker.trace.connect(self._on_batch_trace_event)
        worker.case_finished.connect(self._on_batch_case_finished)
        worker.case_failed.connect(self._on_batch_case_failed)
        worker.finished.connect(self._on_batch_finished)
        worker.cancelled.connect(self._on_batch_cancelled)
        worker.finished.connect(self.worker_thread.quit)
        worker.cancelled.connect(self.worker_thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        self.worker_thread.finished.connect(self._on_worker_thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()
        self._worker = worker

    @Slot(str, int, int)
    def _on_batch_case_started(self, case_id: str, index: int, total: int):
        self._reset_live_pipeline(case_id)
        raw = self._batch_case_texts.get(case_id, "")
        self.composer.setPlainText(raw)
        self.pipeline_view.clear()
        self.stage_label.setText(f"[{index}/{total}] {case_id} — starting")
        self.batch_view.appendPlainText(f"[{index}/{total}] {case_id}: STARTED")
        self._append_user_message(f"{case_id} (batch run)\n\n{raw}")

    @Slot(str, str, str)
    def _on_batch_progress(self, case_id: str, stage: str, detail: str):
        self.stage_label.setText(f"{case_id} — {stage}")
        self.pipeline_view.appendPlainText(f"[{case_id}] [{stage}] {detail}")

    @Slot(str, object)
    def _on_batch_case_finished(self, case_id: str, result):
        self.current_result = result
        self.failure_diagnostics = None
        self._display_result(result)
        record = self._save_batch_result(case_id, result=result)
        self.batch_records.append(record)
        elapsed = sum(x.elapsed_seconds for x in result.stats)
        semantic_status = record.get("semantic_acceptance", "NOT_CHECKED")
        self.batch_view.appendPlainText(
            f"{case_id}: EXECUTION=PASS | SEMANTIC={semantic_status} | LLM calls={len(result.stats)} | "
            f"wall={elapsed:.1f}s | repairs={'yes' if result.repair_performed else 'no'}"
        )
        self._append_assistant_message(
            f"{case_id} batch execution completed. Semantic acceptance: {semantic_status}.\n\n" + result.final_report
        )

    @Slot(str, str, object, object, object, object, object)
    def _on_batch_case_failed(self, case_id: str, message: str, validated, canonical, attempts, stats, repair_log):
        self.current_result = None
        failure = self._failure_payload(message, validated, canonical, attempts, stats, repair_log)
        self.failure_diagnostics = failure
        record = self._save_batch_result(case_id, failure=failure)
        self.batch_records.append(record)
        self._display_failure(message, validated, canonical, attempts, stats, repair_log)
        self.batch_view.appendPlainText(f"{case_id}: EXECUTION=FAILED | SEMANTIC=NOT_EVALUATED | {message}")
        self._append_assistant_message(f"{case_id} batch analysis failed deterministic validation.\n\n{message}")

    @Slot(object)
    def _on_batch_finished(self, worker_summary):
        self.batch_active = False
        self._set_busy(False)
        self.progress.setRange(0, 100)
        execution_passed = sum(1 for x in self.batch_records if x.get("execution_status") == "PASS")
        semantic_checked = [x for x in self.batch_records if x.get("semantic_acceptance") in {"PASS", "FAIL"}]
        semantic_passed = sum(1 for x in semantic_checked if x.get("semantic_acceptance") == "PASS")
        total = len(self.batch_records)
        self.progress.setValue(round((total / self.batch_expected_total) * 100) if self.batch_expected_total else 0)
        self.stage_label.setText(
            f"Sequential batch complete — execution {execution_passed}/{total}; semantic {semantic_passed}/{len(semantic_checked)}"
        )

        summary = {
            "harness_version": __version__,
            "baseline_version": "0.5.2",
            "semantic_baseline_version": "0.5.2",
            "execution_mode": "SEQUENTIAL",
            "batch_label": self.batch_label,
            "bundle_source": self.batch_bundle_source,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "execution_summary": {"passed": execution_passed, "total": total},
            "semantic_acceptance_summary": {"passed": semantic_passed, "checked": len(semantic_checked)},
            "results": self.batch_records,
            "worker_summary": worker_summary,
        }
        if self.batch_output_dir is not None:
            summary_path = self.batch_output_dir / f"{self.batch_summary_stem}.json"
            summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            md_path = self.batch_output_dir / f"{self.batch_summary_stem}.md"
            rows = [
                f"# RCA v{__version__} Sequential Batch",
                "",
                f"**Batch:** {self.batch_label}",
                f"**Execution mode:** SEQUENTIAL",
            ]
            if self.batch_bundle_source:
                rows.append(f"**Bundle source:** {self.batch_bundle_source}")
            rows.extend([
                "",
                f"**Execution:** {execution_passed}/{total} passed",
                f"**Semantic acceptance:** {semantic_passed}/{len(semantic_checked)} passed (checked cases)",
                "",
                "| Case | Execution Status | Semantic Acceptance | Source | Report | Session |",
                "|---|---|---|---|---|---|",
            ])
            for rec in self.batch_records:
                rows.append(
                    f"| {rec.get('case','')} | {rec.get('execution_status','')} | {rec.get('semantic_acceptance','')} | "
                    f"{rec.get('source_file','')} | {rec.get('report_file','')} | {rec.get('session_file','')} |"
                )
            md_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            self.batch_view.appendPlainText("")
            self.batch_view.appendPlainText(f"Summary JSON: {summary_path}")
            self.batch_view.appendPlainText(f"Summary MD:   {md_path}")

        self.tabs.setCurrentWidget(self.batch_view)
        title = "Sequential Batch"
        message = (
            f"Sequential batch complete. Execution: {execution_passed}/{total} passed. "
            f"Semantic acceptance: {semantic_passed}/{len(semantic_checked)} passed.\n\nResults: {self.batch_output_dir}"
        )
        all_execution_ok = execution_passed == total and total > 0
        all_semantic_ok = not semantic_checked or semantic_passed == len(semantic_checked)
        if all_execution_ok and all_semantic_ok:
            QMessageBox.information(self, title, message)
        else:
            QMessageBox.warning(self, title, message)

    def _save_batch_result(self, case_id: str, result=None, failure=None):
        alias = safe_case_alias(case_id)
        expected_case = self._batch_expectations.get(case_id)
        record = {
            "case": case_id,
            "execution_status": "PASS" if result is not None else "FAILED",
            # Backward-compatible alias; new consumers must use execution_status.
            "status": "PASS" if result is not None else "FAILED",
            "semantic_acceptance": "NOT_EVALUATED" if result is None else "NOT_CHECKED",
            "source_file": self._batch_source_files.get(case_id, ""),
        }
        if self.batch_output_dir is None:
            return record
        if result is not None:
            report_path = self.batch_output_dir / f"{alias}-RCA_Report_v{__version__}.md"
            session_path = self.batch_output_dir / f"{alias}-RCA_Session_v{__version__}.json"
            report_path.write_text(result.final_report, encoding="utf-8")
            session_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
            acceptance = evaluate_semantic_acceptance(result, expected_case)
            record.update({
                "report_file": report_path.name,
                "session_file": session_path.name,
                "semantic_acceptance": acceptance["status"],
                "expected_vs_actual": acceptance,
                "evaluation_statuses": {
                    rr.analysis.requirement_id: rr.evaluation_status.value for rr in result.validated.requirement_results
                },
                "repair_performed": bool(result.repair_performed),
                "llm_calls": len(result.stats),
                "llm_wall_seconds": sum(x.elapsed_seconds for x in result.stats),
            })
        else:
            session_path = self.batch_output_dir / f"{alias}-RCA_Failed_Session_v{__version__}.json"
            session_path.write_text(json.dumps(failure, indent=2, ensure_ascii=False), encoding="utf-8")
            record.update({
                "session_file": session_path.name,
                "message": failure.get("message", ""),
                "expected_vs_actual": {
                    "status": "NOT_EVALUATED",
                    "reason": "Pipeline execution failed before a final validated result was available.",
                    "expected": expected_case.get("expected", {}) if expected_case else {},
                    "manual_criteria": expected_case.get("must_not", []) if expected_case else [],
                },
            })
        return record

    def _display_result(self, result):
        self.report_view.setMarkdown(result.final_report)
        self.json_view.setPlainText(result.raw_semantic_json)
        self.validation_view.setPlainText(self._validation_text(result.validated.issues))
        self.canonical_view.setPlainText(json.dumps(result.canonical_case.model_dump(mode="json"), indent=2, ensure_ascii=False))
        self.stats_view.setPlainText(self._stats_text(result.stats, result.repair_performed))
        self.attempts_view.setPlainText(self._attempts_text(result.attempts))
        self.repair_view.setPlainText(self._repair_log_text(result.repair_log))
        self.export_md_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)

    @staticmethod
    def _failure_payload(message, validated, canonical, attempts, stats, repair_log):
        return {
            "status": "FAILED",
            "message": message,
            "canonical_case": canonical.model_dump(mode="json") if canonical is not None else None,
            "validated": validated.model_dump(mode="json") if validated is not None else None,
            "attempts": [a.model_dump(mode="json") for a in (attempts or [])],
            "stats": [x.model_dump(mode="json") for x in (stats or [])],
            "repair_log": [x.model_dump(mode="json") for x in (repair_log or [])],
        }

    def _display_failure(self, message, validated, canonical, attempts, stats, repair_log):
        self.attempts_view.setPlainText(self._attempts_text(attempts or []))
        self.repair_view.setPlainText(self._repair_log_text(repair_log or []))
        self.stats_view.setPlainText(self._stats_text(stats or [], bool((attempts or [])[1:])))
        self.export_json_btn.setEnabled(True)
        if canonical is not None:
            self.canonical_view.setPlainText(json.dumps(canonical.model_dump(mode="json"), indent=2, ensure_ascii=False))
        if validated is not None:
            self.validation_view.setPlainText(self._validation_text(validated.issues))
            self.json_view.setPlainText(json.dumps(validated.semantic.model_dump(mode="json"), indent=2, ensure_ascii=False))

    def _reset_live_pipeline(self, case_label: str = ""):
        self._pipeline_trace_events = {}
        self._pipeline_trace_case = case_label
        self.live_stage_list.clear()
        self.live_stage_summary.clear()
        self.live_stage_input.clear()
        self.live_stage_output.clear()
        self.live_pipeline_case_label.setText(case_label or "No active analysis")

    @staticmethod
    def _trace_status_prefix(status: str) -> str:
        return {
            "running": "▶",
            "complete": "✓",
            "attention": "!",
            "failed": "✕",
            "skipped": "○",
            "cancelled": "■",
        }.get((status or "").lower(), "•")

    @Slot(object)
    def _on_trace_event(self, event):
        if not isinstance(event, dict):
            return
        stage_id = str(event.get("stage_id", "")).strip()
        if not stage_id:
            return
        is_new = stage_id not in self._pipeline_trace_events
        self._pipeline_trace_events[stage_id] = dict(event)
        keys = list(self._pipeline_trace_events)
        row = keys.index(stage_id)
        label = f"{self._trace_status_prefix(str(event.get('status','')))}  {event.get('title', stage_id)}"
        if is_new:
            self.live_stage_list.addItem(label)
        else:
            self.live_stage_list.item(row).setText(label)
        if self.live_pipeline_follow.isChecked() or self.live_stage_list.currentRow() < 0:
            self.live_stage_list.setCurrentRow(row)
        elif self.live_stage_list.currentRow() == row:
            self._render_live_stage(row)

    @Slot(str, object)
    def _on_batch_trace_event(self, case_id: str, event):
        if self._pipeline_trace_case != case_id:
            self._reset_live_pipeline(case_id)
        self._on_trace_event(event)

    @Slot(int)
    def _on_live_stage_selected(self, row: int):
        self._render_live_stage(row)

    def _render_live_stage(self, row: int):
        keys = list(self._pipeline_trace_events)
        if row < 0 or row >= len(keys):
            return
        event = self._pipeline_trace_events[keys[row]]
        title = html.escape(str(event.get("title", "Pipeline Stage")))
        status = html.escape(str(event.get("status", "unknown")).upper())
        summary = html.escape(str(event.get("summary", "")))
        status_color = {
            "RUNNING": "#4f8fc9",
            "COMPLETE": "#3b8f62",
            "ATTENTION": "#b8841f",
            "FAILED": "#b34b4b",
            "SKIPPED": "#6b7280",
            "CANCELLED": "#b34b4b",
        }.get(status, "#6b7280")
        self.live_stage_summary.setHtml(
            f"<h3 style='margin:0 0 6px 0'>{title}</h3>"
            f"<p style='margin:0 0 8px 0'><b style='color:{status_color}'>{status}</b></p>"
            f"<p style='margin:0'>{summary}</p>"
        )
        self.live_stage_input.setPlainText(str(event.get("input_text", "")))
        self.live_stage_output.setPlainText(str(event.get("output_text", "")))

    @Slot(str, str)
    def _on_progress(self, stage: str, detail: str):
        self.stage_label.setText(stage)
        self.pipeline_view.appendPlainText(f"[{stage}] {detail}")

    @Slot(object)
    def _on_finished(self, result):
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.stage_label.setText("Complete")
        self.current_result = result
        self.failure_diagnostics = None
        self._display_result(result)
        self._append_assistant_message("Analysis completed and passed deterministic validation.\n\n" + result.final_report)
        self.tabs.setCurrentWidget(self.report_view)

    @Slot(str, object, object, object, object, object)
    def _on_failed(self, message: str, validated, canonical, attempts, stats, repair_log):
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.stage_label.setText("Failed")
        self.failure_diagnostics = self._failure_payload(message, validated, canonical, attempts, stats, repair_log)
        self._display_failure(message, validated, canonical, attempts, stats, repair_log)
        if validated is not None:
            self.tabs.setCurrentWidget(self.validation_view)
        elif canonical is not None:
            self.tabs.setCurrentWidget(self.canonical_view)
        self._append_assistant_message("Analysis stopped because deterministic validation did not pass.\n\n" + message)
        QMessageBox.critical(self, "Analysis failed", message)

    @Slot()
    def stop_analysis(self):
        if not (self.worker_thread and self.worker_thread.isRunning()) or self._worker is None:
            return
        self.stop_btn.setEnabled(False)
        self.stage_label.setText("Stopping…")
        self.pipeline_view.appendPlainText("[STOP] User requested cancellation. No partial RCA result will be accepted.")
        try:
            self._worker.request_cancel()
        except Exception as exc:
            self.pipeline_view.appendPlainText(f"[STOP] Cancellation request error: {exc}")

    def _mark_live_pipeline_cancelled(self, message: str):
        for stage_id, event in list(self._pipeline_trace_events.items()):
            if str(event.get("status", "")).lower() == "running":
                updated = dict(event)
                updated["status"] = "cancelled"
                updated["summary"] = message or "Stopped by user before this stage completed."
                previous = str(updated.get("output_text", ""))
                updated["output_text"] = (previous + "\n\n" if previous else "") + "CANCELLED: no partial stage output was accepted."
                self._pipeline_trace_events[stage_id] = updated
                row = list(self._pipeline_trace_events).index(stage_id)
                item = self.live_stage_list.item(row)
                if item is not None:
                    item.setText(f"{self._trace_status_prefix('cancelled')}  {updated.get('title', stage_id)}")
                if self.live_stage_list.currentRow() == row:
                    self._render_live_stage(row)

    @Slot(str)
    def _on_cancelled(self, message: str):
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.stage_label.setText("Stopped by user")
        self.current_result = None
        self.failure_diagnostics = None
        self.export_md_btn.setEnabled(False)
        self.export_json_btn.setEnabled(False)
        self._mark_live_pipeline_cancelled(message)
        self.pipeline_view.appendPlainText(f"[STOPPED] {message}")
        self._append_assistant_message("Analysis was stopped by the user. No partial result was promoted to a final RCA report.")

    @Slot(str, object)
    def _on_batch_cancelled(self, message: str, worker_summary):
        self.batch_active = False
        self._set_busy(False)
        self.progress.setRange(0, 100)
        completed = len(self.batch_records)
        self.progress.setValue(round((completed / self.batch_expected_total) * 100) if self.batch_expected_total else 0)
        self.stage_label.setText(f"Batch stopped by user — {completed}/{self.batch_expected_total} completed")
        self._mark_live_pipeline_cancelled(message)
        self.batch_view.appendPlainText("")
        self.batch_view.appendPlainText(f"BATCH ABORTED BY USER: {message}")
        self.batch_view.appendPlainText("Completed cases were preserved; the active case produced no accepted partial result; remaining cases were not started.")
        self.tabs.setCurrentWidget(self.batch_view)

    @Slot()
    def _on_worker_thread_finished(self):
        self.worker_thread = None
        self._worker = None

    def _set_busy(self, busy: bool):
        self.analyze_btn.setEnabled(not busy)
        self.run_all_tests_btn.setEnabled(not busy)
        self.run_bundle_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)
        self.load_example_btn.setEnabled(not busy)
        self.load_test2_btn.setEnabled(not busy)
        self.load_test3_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    @Slot()
    def clear_case(self):
        self.composer.clear()
        self.transcript.clear()
        self.report_view.clear()
        self.pipeline_view.clear()
        self.batch_view.clear()
        self.validation_view.clear()
        self.canonical_view.clear()
        self.json_view.clear()
        self.stats_view.clear()
        self.attempts_view.clear()
        self.repair_view.clear()
        self._reset_live_pipeline()
        self.current_result = None
        self.failure_diagnostics = None
        self.batch_records = []
        self.batch_output_dir = None
        self.batch_label = "Sequential Batch"
        self.batch_bundle_source = ""
        self.batch_expected_total = 0
        self._batch_source_files = {}
        self._batch_expectations = {}
        self.export_md_btn.setEnabled(False)
        self.export_json_btn.setEnabled(False)
        self.progress.setValue(0)
        self.stage_label.setText("Ready")

    @Slot()
    def load_example(self):
        path = Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt"
        if path.exists():
            self.composer.setPlainText(path.read_text(encoding="utf-8"))

    @Slot()
    def load_test2(self):
        path = Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt"
        if path.exists():
            self.composer.setPlainText(path.read_text(encoding="utf-8"))

    @Slot()
    def load_test3(self):
        path = Path(__file__).resolve().parent.parent / "examples" / "TEST-003.txt"
        if path.exists():
            self.composer.setPlainText(path.read_text(encoding="utf-8"))

    @Slot()
    def export_report(self):
        if not self.current_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Final Report", "RCA_Report.md", "Markdown (*.md);;All files (*.*)")
        if path:
            Path(path).write_text(self.current_result.final_report, encoding="utf-8")

    @Slot()
    def export_session(self):
        payload = None
        default_name = "RCA_Session.json"
        if self.current_result:
            payload = self.current_result.model_dump(mode="json")
        elif self.failure_diagnostics:
            payload = self.failure_diagnostics
            default_name = "RCA_Failed_Session.json"
        if payload is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export RCA Session", default_name, "JSON (*.json);;All files (*.*)")
        if path:
            Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _append_user_message(self, text: str):
        light = str(self.theme_combo.currentData() or "dark") == "light"
        bg = "#e8f1fb" if light else "#223142"
        fg = "#17202a" if light else "#e8edf2"
        self.transcript.append(
            f'<div style="margin:8px 0;padding:10px;border-radius:8px;background:{bg};color:{fg};">'
            '<b>Case input</b><br><pre style="white-space:pre-wrap;">' + html.escape(text) + '</pre></div>'
        )

    def _append_assistant_message(self, text: str):
        light = str(self.theme_combo.currentData() or "dark") == "light"
        bg = "#edf7ef" if light else "#1d2822"
        fg = "#17202a" if light else "#e8edf2"
        self.transcript.append(
            f'<div style="margin:8px 0;padding:10px;border-radius:8px;background:{bg};color:{fg};">'
            '<b>RCA Analyst</b><br><pre style="white-space:pre-wrap;">' + html.escape(text) + '</pre></div>'
        )

    @staticmethod
    def _validation_text(issues) -> str:
        if not issues:
            return "PASS — no deterministic validation issues."
        return "\n".join(f"{i.severity.value:<7} {i.code:<38} {i.path}\n        {i.message}" for i in issues)

    @staticmethod
    def _attempts_text(attempts) -> str:
        if not attempts:
            return "No persisted LLM/validation attempts are available."
        blocks = []
        for a in attempts:
            issues = a.validation_issues or []
            critical = [i for i in issues if i.severity.value == "ERROR"]
            warnings = [i for i in issues if i.severity.value == "WARNING"]
            blocks.append(
                f"=== Call {a.call_index}: {a.stage} ===\n"
                f"Role: {a.model_role or 'UNSPECIFIED'}\n"
                f"Transport: {a.transport or '<unknown>'}\n"
                f"Finish reason: {a.finish_reason or '<not returned>'}\n"
                f"Elapsed: {a.stats.elapsed_seconds:.1f}s ({a.stats.elapsed_seconds/60:.1f} min)\n"
                f"Prompt/Completion/Reasoning: {a.stats.prompt_tokens}/{a.stats.completion_tokens}/{a.stats.reasoning_tokens}\n"
                f"Structured/API retries: {a.stats.retries}\n"
                f"Validation: {len(critical)} error(s), {len(warnings)} warning(s)\n"
            )
            if a.retry_diagnostics:
                blocks.append("--- Retry diagnostics ---\n" + "\n".join(f"- {x}" for x in a.retry_diagnostics))
            if issues:
                blocks.append("\n".join(
                    f"{i.severity.value:<7} {i.code} — {i.path}\n        {i.message}" for i in issues
                ))
            else:
                blocks.append("PASS — no deterministic validation issues.")
            blocks.append("\n--- Raw LLM response ---\n" + (a.raw_llm_json or "<empty>"))
            if a.reasoning_content:
                blocks.append("\n--- Visible reasoning content returned by API ---\n" + a.reasoning_content)
            blocks.append("\n--- Normalized semantic object ---\n" + (a.normalized_semantic_json or "<empty>"))
        return "\n\n".join(blocks)

    @staticmethod
    def _repair_log_text(events) -> str:
        if not events:
            return "No repair routing was needed."
        blocks = []
        for e in events:
            blocks.append(
                f"Pass {e.pass_index} — {e.route.value}\n"
                f"  Outcome:       {e.outcome}\n"
                f"  Model:         {e.model or '<none>'}\n"
                f"  Elapsed:       {e.elapsed_seconds:.3f} s\n"
                f"  Requirements:  {', '.join(e.requirement_ids) if e.requirement_ids else '<none/global>'}\n"
                f"  Issue codes:   {', '.join(e.issue_codes) if e.issue_codes else '<none>'}\n"
                f"  Details:       {e.details}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _stats_text(stats, repair_performed: bool) -> str:
        if not stats:
            return "No API usage statistics were returned by the endpoint."
        parts = []
        total_elapsed = 0.0
        for n, s in enumerate(stats, start=1):
            total_elapsed += s.elapsed_seconds
            parts.append(
                f"Call {n}\n"
                f"  Model:              {s.model}\n"
                f"  Endpoint:           {s.endpoint}\n"
                f"  Elapsed:            {s.elapsed_seconds:.1f} s ({s.elapsed_seconds/60:.1f} min)\n"
                f"  Prompt tokens:      {s.prompt_tokens}\n"
                f"  Completion tokens:  {s.completion_tokens}\n"
                f"  Reasoning tokens:   {s.reasoning_tokens}\n"
                f"  Total tokens:       {s.total_tokens}\n"
                f"  API retries:        {s.retries}\n"
            )
        parts.append(f"Total LLM wall time: {total_elapsed:.1f} s ({total_elapsed/60:.1f} min)")
        parts.append(f"Repair performed: {'Yes' if repair_performed else 'No'}")
        parts.append("Note: token/detail fields depend on what the LM Studio OpenAI-compatible endpoint returns for the selected runtime/model.")
        return "\n".join(parts)


def run_gui():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(DARK_STYLE)
    win = MainWindow()
    win.show()
    return app.exec()
