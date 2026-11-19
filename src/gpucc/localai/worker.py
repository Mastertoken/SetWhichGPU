"""Runs the (blocking) local AI queries on their own thread; results come back as Qt signals."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from gpucc.localai import client
from gpucc.localai.runtimes import RUNTIMES, ModelReport

log = logging.getLogger(__name__)


class LocalAiWorker(QObject):
    report_ready = Signal(object)  # ModelReport

    @Slot(str)
    def query(self, runtime_name: str) -> None:
        threading.current_thread().name = "gpucc-localai"
        runtime = next((r for r in RUNTIMES if r.name == runtime_name), None)
        if runtime is None:
            return
        try:
            report = client.query(runtime)
        except Exception:
            log.exception("local AI query failed")
            report = ModelReport(runtime.name, False, problem="invalid")
        self.report_ready.emit(report)  # always answer, otherwise LocalAiThread stays busy


class LocalAiThread(QObject):
    """Owns the QThread. request() is ignored while a query is still running (no pile-up)."""

    report_ready = Signal(object)
    _request = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._qthread = QThread()
        self._qthread.setObjectName("gpucc-localai")
        self._worker = LocalAiWorker()
        self._worker.moveToThread(self._qthread)
        self._request.connect(self._worker.query)
        self._worker.report_ready.connect(self._on_report)
        self._busy = False
        self._started = False

    def request(self, runtime_name: str) -> None:
        if self._busy:
            return
        if not self._started:  # the thread only exists once the feature is actually used
            self._qthread.start()
            self._started = True
        self._busy = True
        self._request.emit(runtime_name)

    def _on_report(self, report: object) -> None:
        self._busy = False
        self.report_ready.emit(report)

    def shutdown(self, timeout_ms: int = 2000) -> None:
        if self._started:
            self._qthread.quit()
            if not self._qthread.wait(timeout_ms):
                log.warning("local AI thread did not stop in time")
