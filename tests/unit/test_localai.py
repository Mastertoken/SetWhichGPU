"""Local AI runtimes (ADR-0003): parsing, loopback-only client, overlay lines."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from gpucc.core.models import Confidence, ObservedGpu, ProcessGpuSummary, TargetApp
from gpucc.localai import client
from gpucc.localai.runtimes import (
    BIONIC,
    KOBOLDCPP,
    LEMONADE,
    LLAMA_CPP,
    LM_STUDIO,
    MAX_NAME_LEN,
    OLLAMA,
    SD_WEBUI,
    TEXTGEN_WEBUI,
    LoadedModel,
    ModelReport,
    parse_koboldcpp_model,
    parse_lemonade_health,
    parse_llamacpp_models,
    parse_lmstudio_v0,
    parse_lmstudio_v1,
    parse_ollama_ps,
    parse_sd_webui_options,
    parse_textgen_model_info,
    port_from,
    runtime_for,
)
from gpucc.ui.overlay.viewmodel import build_state, model_lines

GIB = 1 << 30

OLLAMA_PS = {
    "models": [
        {
            "name": "gemma4",
            "model": "gemma4",
            "size": 6591830464,
            "digest": "c6eb",
            "details": {"format": "gguf", "family": "gemma4", "parameter_size": "8.0B", "quantization_level": "Q4_K_M"},
            "expires_at": "2025-10-17T16:47:07.93355-07:00",
            "size_vram": 5333539264,
            "context_length": 4096,
        }
    ]
}
LMSTUDIO_V1 = {
    "models": [
        {
            "type": "llm",
            "key": "google/gemma-4-26b-a4b",
            "display_name": "Gemma 4 26B A4B",
            "quantization": {"name": "Q4_K_M", "bits_per_weight": 4},
            "size_bytes": 17990911801,
            "params_string": "26B-A4B",
            "loaded_instances": [{"id": "google/gemma-4-26b-a4b", "config": {"context_length": 4096}}],
        },
        {"type": "llm", "key": "deepseek-r1", "display_name": "DeepSeek R1", "loaded_instances": []},
    ]
}
LMSTUDIO_V0 = {
    "data": [
        {"id": "qwen2-vl-7b-instruct", "state": "loaded", "quantization": "4bit"},
        {"id": "other", "state": "not-loaded"},
    ]
}


# ----------------------------------------------------------------------------- parsing


def test_parse_ollama():
    (m,) = parse_ollama_ps(OLLAMA_PS)
    assert m == LoadedModel("gemma4", "8.0B · Q4_K_M", 6591830464, 5333539264)
    assert parse_ollama_ps({"models": []}) == ()


def test_parse_lmstudio_only_loaded_models():
    assert parse_lmstudio_v1(LMSTUDIO_V1) == (LoadedModel("Gemma 4 26B A4B", "26B-A4B · Q4_K_M", 17990911801),)
    assert parse_lmstudio_v0(LMSTUDIO_V0) == (LoadedModel("qwen2-vl-7b-instruct", "4bit"),)


@pytest.mark.parametrize("parse", [parse_ollama_ps, parse_lmstudio_v1, parse_lmstudio_v0])
@pytest.mark.parametrize("data", [None, [], "x", 3])
def test_unexpected_answers_are_rejected(parse, data):
    with pytest.raises(ValueError):
        parse(data)


def test_untrusted_fields_are_sanitised():
    data = {
        "models": [
            {"name": "evil\x1b[31m\nname" + "x" * 200, "size": -5, "size_vram": True, "details": "nope"},
            {"name": 42},
            "garbage",
        ]
    }
    (m,) = parse_ollama_ps(data)
    assert "\x1b" not in m.name and "\n" not in m.name
    assert len(m.name) == MAX_NAME_LEN and m.name.endswith("…")
    assert (m.size_bytes, m.vram_bytes, m.detail) == (None, None, "")


@pytest.mark.parametrize(
    ("value", "port"),
    [
        ("", 11434),
        ("127.0.0.1:8080", 8080),
        ("http://0.0.0.0:9000/", 9000),
        (":7000", 7000),
        ("6000", 6000),
        ("0.0.0.0", 11434),
        ("host:99999", 11434),
        ("garbage", 11434),
    ],
)
def test_port_from_environment(value, port):
    assert port_from({"OLLAMA_HOST": value}, "OLLAMA_HOST", 11434) == port


def test_port_from_app_settings(tmp_path):
    cfg = tmp_path / BIONIC.config_file
    assert BIONIC.ports(env={}, home=tmp_path) == (1235,)  # no settings file yet
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"port": 4321, "networkInterface": "127.0.0.1"}', encoding="utf-8")
    assert BIONIC.ports(env={}, home=tmp_path) == (4321,)
    assert BIONIC.ports(env={"GPUCC_BIONIC_PORT": "5555"}, home=tmp_path) == (5555,)  # explicit override wins
    for broken in ('{"port": "1"}', '{"port": 70000}', "[1]", "not json"):
        cfg.write_text(broken, encoding="utf-8")
        assert BIONIC.ports(env={}, home=tmp_path) == (1235,)


def test_runtime_for_process_names():
    assert runtime_for(r"C:\Users\x\AppData\Local\Programs\Bionic\Bionic.exe") is BIONIC
    assert runtime_for(r"C:\Users\x\AppData\Local\Programs\Ollama\lib\ollama\llama-server.exe") is OLLAMA
    assert runtime_for(r"D:\llama.cpp\llama-server.exe") is LLAMA_CPP  # plain llama.cpp is not Ollama
    assert runtime_for("ollama.exe") is OLLAMA
    assert runtime_for("Ollama App.exe") is OLLAMA
    assert runtime_for("LM Studio.exe") is LM_STUDIO
    assert runtime_for("python.exe") is None
    assert runtime_for(None) is None


@pytest.mark.parametrize(
    ("path", "runtime"),
    [
        (r"C:\Users\x\AppData\Local\lemonade_server\bin\llamacpp\vulkan\llama-server.exe", LEMONADE),
        (r"C:\Program Files\Lemonade Server\lemonade-server.exe", LEMONADE),
        (r"D:\Tools\koboldcpp-nocuda.exe", KOBOLDCPP),
        (r"D:\Tools\koboldcpp.exe", KOBOLDCPP),
        (r"E:\stable-diffusion-webui\venv\Scripts\python.exe", SD_WEBUI),
        (r"E:\webui_forge_cu121_torch231\system\python\python.exe", SD_WEBUI),
        (r"E:\StabilityMatrix\Packages\Stable Diffusion WebUI reForge\venv\Scripts\python.exe", SD_WEBUI),
        (r"E:\automatic\venv\Scripts\python.exe", SD_WEBUI),
        (r"E:\text-generation-webui\installer_files\env\python.exe", TEXTGEN_WEBUI),
        (r"E:\ComfyUI\venv\Scripts\python.exe", None),  # no query for the loaded model exists
        (r"C:\Python313\python.exe", None),
    ],
)
def test_more_runtimes_by_path(path, runtime):
    assert runtime_for(path) is runtime


def test_parse_llamacpp_models_and_router_mode():
    single = {
        "object": "list",
        "data": [{"id": "../models/Llama-3.1-8B-Q4_K_M.gguf", "meta": {"n_params": 8030261248, "size": 4920733696}}],
    }
    assert parse_llamacpp_models(single) == (LoadedModel("Llama-3.1-8B-Q4_K_M", "8.0B", 4920733696),)
    router = {
        "data": [
            {"id": "ggml-org/gemma-3-4b-it-GGUF:Q4_K_M", "status": {"value": "loaded"}},
            {"id": "other", "status": {"value": "unloaded"}},
            {"id": "third", "status": {"value": "loading"}},
        ]
    }
    assert [m.name for m in parse_llamacpp_models(router)] == ["gemma-3-4b-it-GGUF:Q4_K_M"]


def test_parse_koboldcpp():
    assert parse_koboldcpp_model({"result": "koboldcpp/Mistral-7B-Q5"}) == (LoadedModel("Mistral-7B-Q5"),)
    assert parse_koboldcpp_model({"result": "inactive"}) == ()


def test_parse_lemonade():
    health = {
        "status": "ok",
        "model_loaded": "Qwen3-0.6B-GGUF",
        "all_models_loaded": [
            {"model_name": "Qwen3-0.6B-GGUF", "type": "llm", "device": "gpu", "loaded": True, "pid": 1},
            {"model_name": "nomic-embed-text-v1-GGUF", "type": "embedding", "device": "gpu", "loaded": True},
        ],
    }
    assert parse_lemonade_health(health) == (
        LoadedModel("Qwen3-0.6B-GGUF", "GPU"),
        LoadedModel("nomic-embed-text-v1-GGUF", "embedding · GPU"),
    )
    assert parse_lemonade_health({"status": "ok", "model_loaded": "Old-Model"}) == (LoadedModel("Old-Model"),)
    assert parse_lemonade_health({"status": "ok", "model_loaded": None}) == ()


def test_parse_sd_webui_and_textgen():
    options = {"sd_model_checkpoint": "sdxl\\juggernautXL_v9.safetensors [c9e3e68f89]", "CLIP_stop_at_last_layers": 1}
    assert parse_sd_webui_options(options) == (LoadedModel("juggernautXL_v9", "Checkpoint"),)
    assert parse_sd_webui_options({"sd_model_checkpoint": None}) == ()
    assert parse_textgen_model_info({"model_name": "Qwen2.5-7B", "lora_names": ["style"]}) == (
        LoadedModel("Qwen2.5-7B", "LoRA: style"),
    )
    assert parse_textgen_model_info({"model_name": "None", "lora_names": []}) == ()


# ----------------------------------------------------------------------------- client


class _Handler(BaseHTTPRequestHandler):
    routes: dict = {}

    def do_GET(self):
        status, body = self.routes.get(self.path, (404, {"error": "not found"}))
        raw = json.dumps(body).encode() if not isinstance(body, bytes) else body
        self.send_response(status)
        if status in (301, 302):
            self.send_header("Location", "http://example.com/")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def serve(httpd, routes):
    _Handler.routes = routes
    return httpd.server_address[1]


def test_query_ollama(server, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:1")  # proxies are never used
    port = serve(server, {"/api/ps": (200, OLLAMA_PS)})
    report = client.query(OLLAMA, [port])
    assert report.reachable and report.models[0].name == "gemma4"


def test_lmstudio_falls_back_to_v0(server):
    port = serve(server, {"/api/v0/models": (200, LMSTUDIO_V0)})
    report = client.query(LM_STUDIO, [port])
    assert report.reachable and report.models[0].name == "qwen2-vl-7b-instruct"


def test_token_protected_api(server):
    port = serve(server, {"/api/v1/models": (401, {"error": "unauthorized"})})
    assert client.query(LM_STUDIO, [port]) == ModelReport("LM Studio", False, problem="unauthorized", port=port)


def test_redirects_are_not_followed(server):
    port = serve(server, {"/api/ps": (302, {})})
    report = client.query(OLLAMA, [port])
    assert not report.reachable and report.problem == "invalid"


def test_invalid_json(server):
    port = serve(server, {"/api/ps": (200, b"<html>not json</html>")})
    assert client.query(OLLAMA, [port]).problem == "invalid"


def test_nothing_listening(server):
    port = server.server_address[1]
    server.shutdown()
    server.server_close()
    report = client.query(OLLAMA, [port])
    assert not report.reachable and report.problem == "unreachable"


def test_second_default_port_is_tried(server):
    port = serve(server, {"/api/v1/health": (200, {"status": "ok", "model_loaded": "M"})})
    closed = _free_port()
    report = client.query(LEMONADE, [closed, port])
    assert report.reachable and report.port == port and report.models == (LoadedModel("M"),)


def test_api_switched_off_is_reported(server, discovery):
    port = serve(server, {})  # A1111 without --api: every API path is 404
    report = client.query(SD_WEBUI, [port])
    assert report.problem == "not_found"
    assert model_lines(report, None, discovery) == (
        "Stable Diffusion WebUI läuft ohne API – mit --api starten, um das Modell zu sehen.",
    )


def _free_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_only_loopback_hosts():
    with pytest.raises(ValueError):
        client.fetch_json("192.168.0.10", 11434, "/api/ps")


# ----------------------------------------------------------------------------- overlay

OLLAMA_APP = TargetApp(0, 4242, r"C:\Program Files\Ollama\ollama.exe", "", "")


def test_lines_partial_offload_on_one_gpu(discovery, keys):
    nv = keys["nvidia"]
    observed = ObservedGpu(nv, Confidence.HIGH, (ProcessGpuSummary(nv, 80.0, 5 * GIB, {"Compute": 80.0}),))
    report = ModelReport("Ollama", True, parse_ollama_ps(OLLAMA_PS), port=11434)
    lines = model_lines(report, observed, discovery)
    assert lines[0] == "gemma4 · 8.0B · Q4_K_M · 6,1 GB · 81 % GPU / 19 % CPU"
    assert lines[1] == f"Läuft auf {discovery.by_key(nv).short_name} (gemessen)"


def test_lines_split_over_two_gpus(discovery, keys):
    nv, arc = keys["nvidia"], keys["intel"]
    per_gpu = (ProcessGpuSummary(nv, 50.0, 6 * GIB, {}), ProcessGpuSummary(arc, 40.0, 4 * GIB, {}))
    report = ModelReport("LM Studio", True, (LoadedModel("Big", size_bytes=10 * GIB, instances=2),), port=1234)
    lines = model_lines(report, ObservedGpu(nv, Confidence.LOW, per_gpu), discovery)
    assert lines[0] == "Big ×2 · 10,0 GB"
    assert lines[1].startswith("Auf mehrere GPUs verteilt (gemessen): ") and "6,0 GB" in lines[1]


def test_lines_problems(discovery):
    assert model_lines(None, None, discovery) == ("Frage die Laufzeit ab …",)
    assert model_lines(ModelReport("Ollama", True, ()), None, discovery) == ("Kein Modell geladen",)
    unreachable = model_lines(ModelReport("LM Studio", False, problem="unreachable", port=1234), None, discovery)
    assert "1234" in unreachable[0] and "LM Studio" in unreachable[0]


def test_section_only_when_enabled(discovery):
    common = dict(target=OLLAMA_APP, discovery=discovery, snapshot=None, observed=None, preferred=None, hotkey_text="x")
    off = build_state(**common, ai_runtime="Ollama", ai_enabled=False)
    assert off.ai_title == "" and any("Tray-Menü" in n for n in off.notes)
    on = build_state(**common, ai_runtime="Ollama", ai_enabled=True, ai_report=ModelReport("Ollama", True, ()))
    assert on.ai_title == "GELADENE KI-MODELLE (OLLAMA)" and on.ai_lines == ("Kein Modell geladen",)
    other = build_state(**common, ai_runtime="Ollama", ai_enabled=True, ai_report=ModelReport("LM Studio", True, ()))
    assert other.ai_lines == ("Frage die Laufzeit ab …",)  # never another runtime's answer
    plain = build_state(**common)
    assert plain.ai_title == "" and not any("Tray" in n for n in plain.notes)
