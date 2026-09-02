from __future__ import annotations

import threading
from typing import Optional


class AnalysisCancelled(RuntimeError):
    """Raised when the user requests cancellation of the active RCA run."""


class CancellationToken:
    """Thread-safe cooperative cancellation token shared by GUI, pipeline and model clients."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason = ""
        self._lock = threading.Lock()

    def cancel(self, reason: str = "Stopped by user.") -> None:
        with self._lock:
            if not self._event.is_set():
                self._reason = reason or "Stopped by user."
                self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason or "Stopped by user."

    def throw_if_cancelled(self, stage: Optional[str] = None) -> None:
        if self.cancelled:
            prefix = f"Analysis cancelled during {stage}: " if stage else "Analysis cancelled: "
            raise AnalysisCancelled(prefix + self.reason)
