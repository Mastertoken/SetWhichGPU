"""Which local AI runtimes we know and how their "loaded models" answers are parsed (pure, no I/O).

The runtimes report *which* models are loaded; *where* (which GPU) is still measured by SetWhichGPU
itself from the process's GPU usage. Answers come from other local programs and are treated as
untrusted: only the expected fields are read, strings are sanitised and lengths capped.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

MAX_NAME_LEN = 80
MAX_MODELS = 16
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


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
    problem: str = ""  # "unreachable" | "unauthorized" | "invalid" (only when not reachable)
    port: int = 0


Parser = Callable[[object], tuple[LoadedModel, ...]]


@dataclass(frozen=True, slots=True)
class Runtime:
    name: str
    exe_names: frozenset[str]  # lower-case process names that belong to this runtime
    default_port: int
    port_env: str  # environment variable that may name another port (host part is ignored)
    endpoints: tuple[tuple[str, Parser], ...]  # tried in order; 404 → next one

    def port(self, env: Mapping[str, str] | None = None) -> int:
        return port_from(env if env is not None else os.environ, self.port_env, self.default_port)


def port_from(env: Mapping[str, str], name: str, default: int) -> int:
    """'127.0.0.1:8080', 'http://0.0.0.0:8080', ':8080' or '8080' → 8080. Only the port is used."""
    raw = (env.get(name) or "").strip().rstrip("/")
    match = re.search(r"(?:^|:)(\d{1,5})$", raw)
    if match and 0 < int(match.group(1)) < 65536:
        return int(match.group(1))
    return default


def clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = _CONTROL.sub("", value).strip()
    return text if len(text) <= MAX_NAME_LEN else text[: MAX_NAME_LEN - 1] + "…"


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _dicts(value: object) -> list[dict[str, object]]:
    return [v for v in value if isinstance(v, dict)][:MAX_MODELS] if isinstance(value, list) else []


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def parse_ollama_ps(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/ps → {"models": [{"name", "size", "size_vram", "details": {...}}]}"""
    if not isinstance(data, dict):
        raise ValueError("unexpected answer")
    models = []
    for m in _dicts(data.get("models")):
        name = clean(m.get("name")) or clean(m.get("model"))
        if not name:
            continue
        raw_details = m.get("details")
        details: dict[str, object] = raw_details if isinstance(raw_details, dict) else {}
        models.append(
            LoadedModel(
                name=name,
                detail=_join(clean(details.get("parameter_size")), clean(details.get("quantization_level"))),
                size_bytes=_int(m.get("size")),
                vram_bytes=_int(m.get("size_vram")),
            )
        )
    return tuple(models)


def parse_lmstudio_v1(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/v1/models → {"models": [{"key", "display_name", "loaded_instances": [...], ...}]}"""
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ValueError("unexpected answer")
    models = []
    for m in [v for v in data["models"] if isinstance(v, dict)]:
        instances = m.get("loaded_instances")
        if not isinstance(instances, list) or not instances:
            continue
        name = clean(m.get("display_name")) or clean(m.get("key"))
        if not name:
            continue
        quant = m.get("quantization")
        quant_name = clean(quant.get("name")) if isinstance(quant, dict) else clean(quant)
        models.append(
            LoadedModel(
                name=name,
                detail=_join(clean(m.get("params_string")), quant_name),
                size_bytes=_int(m.get("size_bytes")),
                instances=len(instances),
            )
        )
        if len(models) >= MAX_MODELS:
            break
    return tuple(models)


def parse_lmstudio_v0(data: object) -> tuple[LoadedModel, ...]:
    """GET /api/v0/models (older LM Studio) → {"data": [{"id", "state": "loaded", "quantization"}]}"""
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("unexpected answer")
    return tuple(
        LoadedModel(name=clean(m.get("id")), detail=clean(m.get("quantization")))
        for m in [v for v in data["data"] if isinstance(v, dict)][: MAX_MODELS * 8]
        if m.get("state") == "loaded" and clean(m.get("id"))
    )[:MAX_MODELS]


OLLAMA = Runtime(
    name="Ollama",
    exe_names=frozenset({"ollama.exe", "ollama app.exe", "ollama_llama_server.exe"}),
    default_port=11434,
    port_env="OLLAMA_HOST",
    endpoints=(("/api/ps", parse_ollama_ps),),
)
LM_STUDIO = Runtime(
    name="LM Studio",
    exe_names=frozenset({"lm studio.exe", "lms.exe", "llmster.exe"}),
    default_port=1234,
    port_env="GPUCC_LMSTUDIO_PORT",
    endpoints=(("/api/v1/models", parse_lmstudio_v1), ("/api/v0/models", parse_lmstudio_v0)),
)
RUNTIMES = (OLLAMA, LM_STUDIO)


def runtime_for(exe_name: str | None) -> Runtime | None:
    name = (exe_name or "").lower()
    return next((r for r in RUNTIMES if name in r.exe_names), None)
