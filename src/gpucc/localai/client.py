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
from typing import Any

from gpucc.localai.runtimes import ModelReport, Runtime

log = logging.getLogger(__name__)

LOOPBACK = ("127.0.0.1", "[::1]")
TIMEOUT_S = 1.0
MAX_ANSWER_BYTES = 1 << 20


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


def query(runtime: Runtime, port: int | None = None) -> ModelReport:
    port = port or runtime.port()
    problem = "unreachable"
    for host in LOOPBACK:
        for path, parse in runtime.endpoints:
            try:
                models = parse(fetch_json(host, port, path))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    problem = "unauthorized"
                    break
                problem = "invalid"
                continue  # e.g. 404: older/newer API version → next endpoint
            except (OSError, ValueError) as e:  # URLError/timeouts are OSErrors; ValueError = bad JSON
                if isinstance(e, ValueError):
                    problem = "invalid"
                    continue
                break  # nothing listening on this address → try the next loopback address
            return ModelReport(runtime.name, True, models, port=port)
        if problem != "unreachable":
            break
    log.debug("local AI runtime not answering", extra={"fields": {"runtime": runtime.name, "problem": problem}})
    return ModelReport(runtime.name, False, problem=problem, port=port)
