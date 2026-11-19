"""Which local AI runtimes we know and how their "loaded models" answers are parsed (pure, no I/O
except reading a runtime's own small settings file for its port).

The runtimes report *which* models are loaded; *where* (which GPU) is still measured by SetWhichGPU
itself from the process's GPU usage. Answers come from other local programs and are treated as
untrusted: only the expected fields are read, strings are sanitised and lengths capped.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from gpucc.sanitize import clean_text

MAX_NAME_LEN = 80
MAX_MODELS = 16


@dataclass(frozen=True, slots=True)
class LoadedModel:
    name: str
    detail: str = ""  # e.g. "8.0B · Q4_K_M"
    size_bytes: int | None = None  # memory the loaded model needs in total
    vram_bytes: int | None = None  # part of it in GPU memory (Ollama only)
    instances: int = 1


@dataclass(frozen=True, slots=True)
class ModelReport:
    runtime: str  # display name, e.g. "Ollama"
    reachable: bool
    models: tuple[LoadedModel, ...] = ()
    problem: str = ""  # only when not reachable: "unreachable" | "invalid" | "not_found" | "unauthorized"
    port: int = 0


Parser = Callable[[object], tuple[LoadedModel, ...]]


@dataclass(frozen=True, slots=True)
class Runtime:
    name: str
    endpoints: tuple[tuple[str, Parser], ...]  # tried in order; 404 → next one
    default_ports: tuple[int, ...]  # tried in order (current default first, older defaults after)
    port_env: str  # environment variable that may name another port (host part is ignored)
    exe_names: frozenset[str] = frozenset()  # lower-case process names of this runtime
    exe_prefixes: tuple[str, ...] = ()  # e.g. "koboldcpp" for koboldcpp-nocuda.exe
    # Generic host processes (python.exe, llama-server.exe) only count inside these folders.
    host_exes: frozenset[str] = frozenset()
    path_markers: tuple[str, ...] = ()  # normalised: lower case, "-" and "_" as spaces
    config_file: str = ""  # JSON file below the user profile with a "port" field (LM Studio / Bionic)
    has_server_switch: bool = False  # the local server must be started in the app first
    api_flag: str = ""  # command-line switch that enables the API (e.g. "--api")

    def ports(self, env: Mapping[str, str] | None = None, home: Path | None = None) -> tuple[int, ...]:
        env = env if env is not None else os.environ
        port = port_from(env, self.port_env, 0)
        if port:
            return (port,)
        if self.config_file:
            port = port_from_config((home or Path.home()) / self.config_file, 0)
            if port:
                return (port,)
        return self.default_ports

    def matches(self, exe_path: str) -> bool:
        path = normalise_path(exe_path)
        name = path.rsplit("\\", 1)[-1]
        if name in self.exe_names or any(name.startswith(p) for p in self.exe_prefixes):
            return True
        return name in self.host_exes and any(m in path for m in self.path_markers)


def normalise_path(exe_path: str) -> str:
    return exe_path.replace("/", "\\").replace("-", " ").replace("_", " ").lower()


def port_from(env: Mapping[str, str], name: str, default: int) -> int:
    """'127.0.0.1:8080', 'http://0.0.0.0:8080', ':8080' or '8080' → 8080. Only the port is used."""
    raw = (env.get(name) or "").strip().rstrip("/")
    match = re.search(r"(?:^|:)(\d{1,5})$", raw)
    if match and 0 < int(match.group(1)) < 65536:
        return int(match.group(1))
    return default


def port_from_config(path: Path, default: int) -> int:
    """{"port": 1235, ...} as written by LM Studio / Bionic for their local server."""
    try:
        if path.stat().st_size > 64 * 1024:
            return default
        port = json.loads(path.read_text(encoding="utf-8")).get("port")
    except (OSError, ValueError, AttributeError):
        return default
    return port if isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536 else default


# ----------------------------------------------------------------------------- answer parsing


def clean(value: object) -> str:
    return clean_text(value, MAX_NAME_LEN)


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _dicts(value: object) -> list[dict[str, object]]:
    return [v for v in value if isinstance(v, dict)][: MAX_MODELS * 8] if isinstance(value, list) else []


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _object(data: object, key: str | None = None) -> dict[str, object]:
    if not isinstance(data, dict) or (key is not None and not isinstance(data.get(key), list)):
        raise ValueError("unexpected answer")
    return data


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def _file_name(value: object) -> str:
    """'../models/Llama-3.1-8B-Q4_K_M.gguf' → 'Llama-3.1-8B-Q4_K_M' (paths stay private, names readable)."""
    text = value.replace("\\", "/").rsplit("/", 1)[-1] if isinstance(value, str) else ""
    for suffix in (".gguf", ".safetensors", ".ckpt", ".bin"):
        if text.lower().endswith(suffix):
            text = text[: -len(suffix)]
    return clean(text)


def _params(n: object) -> str:
    count = _int(n)
    return f"{count / 1e9:.1f}B" if count else ""


def parse_ollama_ps(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/ps → {"models": [{"name", "size", "size_vram", "details": {...}}]}"""
    models = []
    for m in _dicts(_object(data).get("models")):
        name = clean(m.get("name")) or clean(m.get("model"))
        if not name:
            continue
        details = _dict(m.get("details"))
        models.append(
            LoadedModel(
                name=name,
                detail=_join(clean(details.get("parameter_size")), clean(details.get("quantization_level"))),
                size_bytes=_int(m.get("size")),
                vram_bytes=_int(m.get("size_vram")),
            )
        )
    return tuple(models[:MAX_MODELS])


def parse_lmstudio_v1(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/v1/models → {"models": [{"key", "display_name", "loaded_instances": [...], ...}]}"""
    models = []
    for m in _dicts(_object(data, "models")["models"]):
        instances = m.get("loaded_instances")
        name = clean(m.get("display_name")) or clean(m.get("key"))
        if not isinstance(instances, list) or not instances or not name:
            continue
        quant = m.get("quantization")
        quant_name = clean(_dict(quant).get("name")) if isinstance(quant, dict) else clean(quant)
        models.append(
            LoadedModel(
                name=name,
                detail=_join(clean(m.get("params_string")), quant_name),
                size_bytes=_int(m.get("size_bytes")),
                instances=len(instances),
            )
        )
    return tuple(models[:MAX_MODELS])


def parse_lmstudio_v0(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/v0/models (older LM Studio) → {"data": [{"id", "state": "loaded", "quantization"}]}"""
    return tuple(
        LoadedModel(name=clean(m.get("id")), detail=clean(m.get("quantization")))
        for m in _dicts(_object(data, "data")["data"])
        if m.get("state") == "loaded" and clean(m.get("id"))
    )[:MAX_MODELS]


def parse_llamacpp_models(data: object) -> tuple[LoadedModel, ...]:
    """GET /v1/models → {"data": [{"id": "<path or alias>", "meta": {"size", "n_params"}}]};
    in router mode each entry also has "status": {"value": "loaded" | "unloaded" | "loading"}."""
    models = []
    for m in _dicts(_object(data, "data")["data"]):
        status = m.get("status")
        if isinstance(status, dict) and status.get("value") != "loaded":
            continue
        name = _file_name(m.get("id"))
        if not name:
            continue
        meta = _dict(m.get("meta"))
        models.append(LoadedModel(name=name, detail=_params(meta.get("n_params")), size_bytes=_int(meta.get("size"))))
    return tuple(models[:MAX_MODELS])


def parse_koboldcpp_model(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/v1/model → {"result": "koboldcpp/<model name>"}"""
    name = clean(_object(data).get("result"))
    name = name.split("/", 1)[1] if name.lower().startswith("koboldcpp/") else name
    return (LoadedModel(name=name),) if name and name.lower() not in ("inactive", "none") else ()


def parse_lemonade_health(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/v1/health → {"model_loaded": "...", "all_models_loaded": [{"model_name", "type", "device", ...}]}"""
    obj = _object(data)
    models = []
    for m in _dicts(obj.get("all_models_loaded")):
        name = clean(m.get("model_name"))
        if not name or m.get("loaded") is False:
            continue
        kind = clean(m.get("type"))
        models.append(
            LoadedModel(name=name, detail=_join("" if kind == "llm" else kind, clean(m.get("device")).upper()))
        )
    if not models and clean(obj.get("model_loaded")):  # older servers: only the last loaded model
        models.append(LoadedModel(name=clean(obj.get("model_loaded"))))
    return tuple(models[:MAX_MODELS])


def parse_sd_webui_options(data: object) -> tuple[LoadedModel, ...]:
    """GET /sdapi/v1/options (A1111, Forge, SD.Next) → {"sd_model_checkpoint": "model.safetensors [hash]", ...}"""
    raw = _object(data).get("sd_model_checkpoint")
    name = _file_name(re.sub(r"\s*\[[0-9a-fA-F]+\]$", "", raw) if isinstance(raw, str) else None)
    return (LoadedModel(name=name, detail="Checkpoint"),) if name else ()


def parse_textgen_model_info(data: object) -> tuple[LoadedModel, ...]:
    """GET /v1/internal/model/info (text-generation-webui) → {"model_name": "...", "lora_names": [...]}"""
    obj = _object(data)
    name = clean(obj.get("model_name"))
    if not name or name.lower() == "none":
        return ()
    raw_loras = obj.get("lora_names")
    loras = [clean(x) for x in raw_loras if clean(x)] if isinstance(raw_loras, list) else []
    return (LoadedModel(name=name, detail=("LoRA: " + ", ".join(loras[:3])) if loras else ""),)


# ----------------------------------------------------------------------------- known runtimes

_LMSTUDIO_API = (("/api/v1/models", parse_lmstudio_v1), ("/api/v0/models", parse_lmstudio_v0))
_PYTHON = frozenset({"python.exe", "pythonw.exe"})
_LLAMA_SERVER = frozenset({"llama server.exe"})  # llama-server.exe, normalised like the path

OLLAMA = Runtime(
    name="Ollama",
    endpoints=(("/api/ps", parse_ollama_ps),),
    default_ports=(11434,),
    port_env="OLLAMA_HOST",
    exe_names=frozenset({"ollama.exe", "ollama app.exe", "ollama llama server.exe"}),
    host_exes=_LLAMA_SERVER,  # Ollama ≥ 0.40 runs models in its own llama-server.exe
    path_markers=("\\ollama\\",),
)
LM_STUDIO = Runtime(
    name="LM Studio",
    endpoints=_LMSTUDIO_API,
    default_ports=(1234,),
    port_env="GPUCC_LMSTUDIO_PORT",
    exe_names=frozenset({"lm studio.exe", "lms.exe", "llmster.exe"}),
    config_file=".lmstudio/.internal/http-server-config.json",
    has_server_switch=True,
)
BIONIC = Runtime(  # LM Studio's newer app; same API, own settings folder and port
    name="Bionic",
    endpoints=_LMSTUDIO_API,
    default_ports=(1235,),
    port_env="GPUCC_BIONIC_PORT",
    exe_names=frozenset({"bionic.exe"}),
    config_file=".lmstudio/apps/bionic/.internal/http-server-config.json",
    has_server_switch=True,
)
LEMONADE = Runtime(  # AMD Lemonade Server; runs models in llama-server.exe below its own folder
    name="Lemonade",
    endpoints=(("/api/v1/health", parse_lemonade_health),),
    default_ports=(13305, 8000),
    port_env="GPUCC_LEMONADE_PORT",
    exe_names=frozenset(
        {"lemonade server.exe", "lemonadeserver.exe", "lemonade router.exe", "lemonade.exe", "lemond.exe"}
    ),
    host_exes=_LLAMA_SERVER | _PYTHON,
    path_markers=("\\lemonade",),
)
KOBOLDCPP = Runtime(
    name="KoboldCpp",
    endpoints=(("/api/v1/model", parse_koboldcpp_model),),
    default_ports=(5001,),
    port_env="GPUCC_KOBOLDCPP_PORT",
    exe_prefixes=("koboldcpp",),
)
LLAMA_CPP = Runtime(  # plain llama.cpp server (after Ollama/Lemonade, which ship their own llama-server.exe)
    name="llama.cpp",
    endpoints=(("/v1/models", parse_llamacpp_models),),
    default_ports=(9931, 8080),
    port_env="LLAMA_ARG_PORT",
    exe_names=_LLAMA_SERVER,
)
SD_WEBUI = Runtime(  # AUTOMATIC1111, Forge, reForge, SD.Next – all Python, recognised by their folder
    name="Stable Diffusion WebUI",
    endpoints=(("/sdapi/v1/options", parse_sd_webui_options),),
    default_ports=(7860, 7861),
    port_env="GPUCC_SDWEBUI_PORT",
    host_exes=_PYTHON,
    path_markers=("stable diffusion webui", "sd webui", "forge", "sdnext", "\\automatic\\"),
    api_flag="--api",
)
TEXTGEN_WEBUI = Runtime(  # oobabooga text-generation-webui (Python)
    name="text-generation-webui",
    endpoints=(("/v1/internal/model/info", parse_textgen_model_info),),
    default_ports=(5000,),
    port_env="GPUCC_TEXTGEN_PORT",
    host_exes=_PYTHON,
    path_markers=("text generation webui", "oobabooga"),
    api_flag="--api",
)
RUNTIMES: tuple[Runtime, ...] = (  # order matters: specific before generic
    OLLAMA,
    LM_STUDIO,
    BIONIC,
    LEMONADE,
    KOBOLDCPP,
    LLAMA_CPP,
    SD_WEBUI,
    TEXTGEN_WEBUI,
)


def runtime_for(exe_path: str | None) -> Runtime | None:
    return next((r for r in RUNTIMES if r.matches(exe_path or "")), None)
