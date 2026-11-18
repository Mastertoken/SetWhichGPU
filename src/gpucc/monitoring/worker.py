"""Qt worker that runs the Sampler on its own thread with an adaptive interval."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from gpucc.core.models import GpuInfo
from gpucc.monitoring.sampler import Sampler

log = logging.getLogger(__name__)

INTERVAL_ACTIVE_MS = 1000
INTERVAL_IDLE_MS = 5000


class MonitoringWorker(QObject):
    """Lives in a QThread. All public slots are invoked via queued signals from the UI thread."""

    snapshot_ready = Signal(object)  # GpuSnapshot

    def __init__(self, sampler_factory: Callable[[], Sampler]) -> None:
        super().__init__()
        self._factory = sampler_factory
        self._sampler: Sampler | None = None
        self._timer: QTimer | None = None
        self._pending_gpus: tuple[GpuInfo, ...] = ()

    @Slot()
    def start(self) -> None:
        threading.current_thread().name = "gpucc-monitoring"  # readable thread name in logs
        # Sources are created on the worker thread and only used there.
        self._sampler = self._factory()
        self._sampler.bind(self._pending_gpus)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sample_now)
        self._timer.start(INTERVAL_IDLE_MS)

    @Slot(object)
    def rebind(self, gpus: Sequence[GpuInfo]) -> None:
        self._pending_gpus = tuple(gpus)
        if self._sampler is not None:
            self._sampler.bind(self._pending_gpus)

    @Slot(int)
    def set_interval(self, ms: int) -> None:
        if self._timer is not None:
            self._timer.start(ms)

    @Slot()
    def sample_now(self) -> None:
        if self._sampler is None:
            return
        try:
            self.snapshot_ready.emit(self._sampler.sample())
        except Exception:
            log.exception("sampling tick failed")

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._sampler is not None:
            self._sampler.close()
            self._sampler = None


class MonitoringThread(QObject):
    """Owns the QThread + worker and exposes thread-safe request signals."""

    request_rebind = Signal(object)
    request_interval = Signal(int)
    request_sample = Signal()
    request_stop = Signal()

    def __init__(self, sampler_factory: Callable[[], Sampler], gpus: Sequence[GpuInfo]) -> None:
        super().__init__()
        # Not named "thread": that would shadow QObject.thread().
        self._qthread = QThread()
        self._qthread.setObjectName("gpucc-monitoring")
        self.worker = MonitoringWorker(sampler_factory)
        self.worker.rebind(gpus)
        self.worker.moveToThread(self._qthread)
        self._qthread.started.connect(self.worker.start)
        self.request_rebind.connect(self.worker.rebind)
        self.request_interval.connect(self.worker.set_interval)
        self.request_sample.connect(self.worker.sample_now)
        self.request_stop.connect(self.worker.stop)

    def start(self) -> None:
        self._qthread.start()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        self.request_stop.emit()
        self._qthread.quit()
        if not self._qthread.wait(timeout_ms):
            log.warning("monitoring thread did not stop in time")
