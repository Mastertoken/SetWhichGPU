"""Asks a local AI runtime which models are loaded.

Hard limits (ADR-0003): only the loopback addresses 127.0.0.1 / ::1 are ever contacted – the host is
not configurable –, no proxy, no redirects, GET only, nothing is sent except the request line, short
timeout, capped answer size. Blocking: call it from a worker thread, never from the UI thread.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from gpucc.localai.runtimes import LoadedModel, ModelReport, Runtime

log = logging.getLogger(__name__)

LOOPBACK = ("127.0.0.1", "[::1]")
TIMEOUT_S = 1.0
MAX_ANSWER_BYTES = 1 << 20
# When several ports fail, report the most informative problem.
_RANK = {"unreachable": 0, "invalid": 1, "not_found": 2, "unauthorized": 3}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # a redirect is answered as an HTTPError instead of being followed


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def fetch_json(host: str, port: int, path: str, timeout: float = TIMEOUT_S) -> object:
    if host not in LOOPBACK:
        raise ValueError("only loopback addresses are allowed")
    request = urllib.request.Request(
        f"http://{host}:{port}{path}", headers={"Accept": "application/json", "User-Agent": "SetWhichGPU"}
    )
    with _OPENER.open(request, timeout=timeout) as response:
        raw = response.read(MAX_ANSWER_BYTES + 1)
    if len(raw) > MAX_ANSWER_BYTES:
        raise ValueError("answer too large")
    return json.loads(raw)


def _ask(runtime: Runtime, host: str, port: int) -> tuple[LoadedModel, ...] | str:
    """The loaded models, or the problem: unreachable / invalid / not_found / unauthorized."""
    problem = "unreachable"
    for path, parse in runtime.endpoints:
        try:
            return parse(fetch_json(host, port, path))
        except urllib.error.HTTPError as e:  # before OSError: HTTPError is one
            if e.code in (401, 403):
                return "unauthorized"
            problem = "not_found" if e.code == 404 else "invalid"  # 404: other API version → next endpoint
        except ValueError:  # bad JSON or an answer of the wrong shape
            problem = "invalid"
        except OSError:  # refused / timeout: nothing (more) to ask here
            return problem
    return problem


def query(runtime: Runtime, ports: Sequence[int] | None = None) -> ModelReport:
    ports = tuple(ports or runtime.ports())
    worst, worst_port = "unreachable", ports[0]
    for port in ports:
        for host in LOOPBACK:
            result = _ask(runtime, host, port)
            if isinstance(result, tuple):
                return ModelReport(runtime.name, True, result, port=port)
            if result != "unreachable":
                if _RANK[result] > _RANK[worst]:
                    worst, worst_port = result, port
                break  # something answers on this port – the other loopback address won't differ
    log.debug("local AI runtime not answering", extra={"fields": {"runtime": runtime.name, "problem": worst}})
    return ModelReport(runtime.name, False, problem=worst, port=worst_port)
