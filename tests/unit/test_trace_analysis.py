"""Regression tests for imported schedules and captured render actions."""

import gzip
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from gpucc.analysis import nsight, renderdoc
from gpucc.analysis.renderdoc import read_report
from gpucc.analysis.timeline import covered_us, load_timeline
from gpucc.ui.overlay.analysis_panel import AnalysisPanel


def test_csv_frame_preserves_other_process_queue_overlap(tmp_path, qtbot):
    path = tmp_path / "gpu.csv"
    path.write_text(
        "start_us,end_us,gpu,engine,queue,process,name,frame\n"
        "10,20,GPU A,Graphics,0,renderer,draw,1\n"
        "11,40,GPU A,Compute,1,inference,kernel,\n"
        "30,50,GPU A,Graphics,0,renderer,draw,2\n"
        "nan,50,GPU A,Copy,0,renderer,invalid,\n",
        encoding="utf-8",
    )
    rows = load_timeline(path)
    assert [r.name for r in rows] == ["draw", "kernel", "draw"]
    panel = AnalysisPanel()
    qtbot.addWidget(panel)
    panel.show_tab(2)
    panel.timeline.set_trace(rows, path.name)
    panel.timeline.frame.setCurrentIndex(2)
    assert len([item for item in panel.timeline.scene.items() if item.toolTip()]) == 2
    panel.timeline.search.setText("inference")
    assert len([item for item in panel.timeline.scene.items() if item.toolTip()]) == 1


def test_compressed_profiler_trace_pairs_nested_events(tmp_path):
    path = tmp_path / "model.json.gz"
    events = [
        {"ph": "M", "pid": 7, "tid": 1, "name": "thread_name", "args": {"name": "CPU"}},
        {"ph": "B", "pid": 7, "tid": 1, "ts": 10, "name": "inference"},
        {"ph": "B", "pid": 7, "tid": 1, "ts": 12, "name": "operator"},
        {"ph": "E", "pid": 7, "tid": 1, "ts": 15},
        {"ph": "E", "pid": 7, "tid": 1, "ts": 20},
        {"ph": "X", "pid": 9, "tid": 1, "ts": 13, "dur": 3, "name": "kernel", "args": {"device": 0, "stream": 7}},
        {"ph": "X", "pid": 9, "tid": 1, "ts": 18, "dur": "Infinity"},
    ]
    path.write_bytes(gzip.compress(json.dumps({"traceEvents": events}).encode()))
    outer, inner, kernel = load_timeline(path)
    assert outer.track == inner.track == "CPU (7:1)"
    assert kernel.track == "0 / 7 / 9:1"
    assert covered_us([(outer.start_us, outer.end_us), (inner.start_us, inner.end_us)]) == 10


def test_invalid_csv_and_traces_report_errors(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text('{"traceEvents": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="No timestamped intervals"):
        load_timeline(path)
    path = tmp_path / "raw.csv"
    path.write_text("Start,End\n0,10", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing timeline CSV columns"):
        load_timeline(path)


def test_nsight_export_combines_cuda_dxgi_and_completed_dma_packets(tmp_path):
    path = tmp_path / "profile.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE StringIds(id INTEGER PRIMARY KEY, value TEXT);
            INSERT INTO StringIds VALUES (1, 'convolution'), (2, 'Present');
            CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL(start,end,globalPid,deviceId,contextId,streamId,demangledName);
            INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES (200, 5400, 117440512, 0, 3, 7, 1);
            CREATE TABLE DXGI_API(start,end,globalTid,frameId,nameId);
            INSERT INTO DXGI_API VALUES (1000, 7000, 117440513, 2, 2);
            CREATE TABLE WDDM_DMA_PACKET_START_EVENTS(
                start,gpu,context,engineType,packetType,ulQueueSubmitSequence,uliSubmissionId,queuePacketContext
            );
            INSERT INTO WDDM_DMA_PACKET_START_EVENTS VALUES (2000, 0, 1, 1, 1, 2, 3, 99);
            INSERT INTO WDDM_DMA_PACKET_START_EVENTS VALUES (2500, 0, 1, 1, 1, 3, 4, 99);
            CREATE TABLE WDDM_DMA_PACKET_STOP_EVENTS(
                start,gpu,context,engineType,packetType,ulQueueSubmitSequence,uliCompletionId
            );
            INSERT INTO WDDM_DMA_PACKET_STOP_EVENTS VALUES (6000, 0, 1, 1, 1, 2, 3);
            CREATE TABLE WDDM_QUEUE_PACKET_START_EVENTS(gpu,context,submitSequence,globalTid);
            INSERT INTO WDDM_QUEUE_PACKET_START_EVENTS VALUES (0, 99, 2, 117440513);
            CREATE TABLE ENUM_WDDM_ENGINE_TYPE(id,label);
            INSERT INTO ENUM_WDDM_ENGINE_TYPE VALUES (1, 'Graphics');
            """
        )
    before = path.read_bytes()
    cuda, dxgi, dma = nsight.load(path)
    assert (cuda.name, cuda.end_us, cuda.track) == ("convolution", 5.4, "CUDA 0 / 3 / 7")
    assert (dxgi.frame, dxgi.name) == ("7 / 2", "Present")
    assert (dma.name, dma.start_us, dma.end_us, dma.process) == ("DMA #2", 2.0, 6.0, "7")
    assert "Graphics" in dma.track
    assert path.read_bytes() == before


def test_capture_report_shows_hierarchy_and_missing_counters(tmp_path, qtbot):
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "api": "Vulkan",
                "actions": [
                    {"depth": 0, "name": "<Lighting>", "event": 10},
                    {"depth": 1, "name": "Draw", "event": 11, "gpu_ms": 1.25, "outputs": "Color"},
                    {"depth": 1, "name": "Dispatch", "event": 12, "gpu_ms": -4},
                    {"depth": 65, "name": "invalid", "event": 13, "gpu_ms": 4},
                ],
            }
        ),
        encoding="utf-8",
    )
    panel = AnalysisPanel()
    qtbot.addWidget(panel)
    panel.show_tab(3)
    panel.passes.set_capture(read_report(path))
    item = panel.passes.tree.topLevelItem(0)
    assert "<Lighting>" in item.text(0)
    assert item.text(1) == "Σ 1.2500"
    assert item.child(0).text(1) == "1.2500"
    assert item.child(1).text(1) == "–"
    assert item.childCount() == 2


def test_renderdoc_replay_handoff_uses_a_private_report_directory(tmp_path, monkeypatch):
    exe = tmp_path / "qrenderdoc.exe"
    exe.touch()
    capture = tmp_path / "capture with spaces.rdc"
    capture.touch()
    data = tmp_path / "data"
    data.mkdir()

    def fake_run(args, **kwargs):
        assert args[:2] == [str(exe), "--python"]
        assert kwargs["timeout"] == 120
        script = Path(args[2])
        assert script.parent.parent == data
        source = script.read_text(encoding="utf-8")
        compile(source, str(script), "exec")
        assert f"CAPTURE = {str(capture)!r}" in source
        script.with_name("report.json").write_text(
            '{"api":"D3D12","actions":[{"depth":0,"event":1,"name":"Frame"}]}', encoding="utf-8"
        )

    monkeypatch.setattr(renderdoc.subprocess, "run", fake_run)
    assert renderdoc.replay(exe, capture, data).actions[0].name == "Frame"
    assert list(data.iterdir()) == []


def test_renderdoc_replay_script_always_ends_qrenderdoc():
    """qrenderdoc keeps its UI open after --python scripts; sys.exit() would only end the script."""
    from gpucc.analysis import renderdoc

    source = "CAPTURE = 'c.rdc'\nREPORT = 'r.json'\nLIMIT = 10\n" + renderdoc._REPLAY
    compile(source, "replay.py", "exec")  # valid Python for RenderDoc's interpreter
    assert renderdoc._REPLAY.rstrip().endswith("os._exit(0)")
    assert "except BaseException:\n    os._exit(2)" in renderdoc._REPLAY
    assert "sys.exit" not in renderdoc._REPLAY
