"""Spikes S5 + S6: PDH GPU counters – sampling cost and per-process GPU attribution.

Read-only. Usage:  uv run python tools/spikes/s5_s6_pdh.py [samples=15] [interval_s=1.0]
"""

from __future__ import annotations

import ctypes
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from ctypes import wintypes as wt
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from s2_adapters import dxgi_adapters, kmt_info  # noqa: E402

pdh = ctypes.WinDLL("pdh")
PDH_MORE_DATA = 0x800007D2
PDH_FMT_DOUBLE = 0x200
PDH_FMT_NOCAP100 = 0x8000


class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [("CStatus", wt.DWORD), ("doubleValue", ctypes.c_double)]


class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = [("szName", wt.LPWSTR), ("FmtValue", PDH_FMT_COUNTERVALUE)]


pdh.PdhOpenQueryW.argtypes = [wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
pdh.PdhAddEnglishCounterW.argtypes = [wt.HANDLE, wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
pdh.PdhCollectQueryData.argtypes = [wt.HANDLE]
pdh.PdhGetFormattedCounterArrayW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
for _f in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterArrayW", "PdhCloseQuery"):
    getattr(pdh, _f).restype = wt.DWORD


def check(rc: int, what: str) -> None:
    if rc != 0:
        raise OSError(f"{what} failed: 0x{rc:08X}")


def read_array(counter: wt.HANDLE, fmt: int) -> dict[str, float]:
    size, count = wt.DWORD(0), wt.DWORD(0)
    rc = pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size), ctypes.byref(count), None)
    if rc != PDH_MORE_DATA:
        check(rc, "PdhGetFormattedCounterArrayW(size)")
        return {}
    buf = ctypes.create_string_buffer(size.value)
    check(pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size), ctypes.byref(count), buf), "PdhGetFormattedCounterArrayW")
    items = ctypes.cast(buf, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
    out: dict[str, float] = {}
    for i in range(count.value):
        it = items[i]
        if it.FmtValue.CStatus in (0, 1):  # VALID / NEW_DATA
            out[it.szName] = out.get(it.szName, 0.0) + it.FmtValue.doubleValue
    return out


kernel32 = ctypes.WinDLL("kernel32")
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def proc_name(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return f"<pid {pid}: kein Zugriff>"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        return Path(buf.value).name if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else f"<pid {pid}>"
    finally:
        kernel32.CloseHandle(h)


ENG_RE = re.compile(r"pid_(\d+)_luid_(0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+)_phys_\d+_eng_\d+_engtype_(.*)$")
PMEM_RE = re.compile(r"pid_(\d+)_luid_(0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+)_phys_\d+$")
AMEM_RE = re.compile(r"luid_(0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+)_phys_\d+$")


def main() -> int:
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

    adapters, _ = dxgi_adapters()
    luid_name: dict[str, str] = {}
    for a in adapters:
        if a["software"]:
            continue
        pci = kmt_info(a["_luid"]).get("pci_address", "")
        valid = not str(pci).startswith("FFFFFFFF")
        luid_name[a["luid"].upper()] = a["description"].replace("(R)", "").replace("(TM)", "") + ("" if valid else " [virtuell/IDD]")

    q = wt.HANDLE()
    check(pdh.PdhOpenQueryW(None, 0, ctypes.byref(q)), "PdhOpenQuery")
    c_eng, c_pmem, c_amem = wt.HANDLE(), wt.HANDLE(), wt.HANDLE()
    check(pdh.PdhAddEnglishCounterW(q, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(c_eng)), "add eng")
    check(pdh.PdhAddEnglishCounterW(q, r"\GPU Process Memory(*)\Dedicated Usage", 0, ctypes.byref(c_pmem)), "add pmem")
    check(pdh.PdhAddEnglishCounterW(q, r"\GPU Adapter Memory(*)\Dedicated Usage", 0, ctypes.byref(c_amem)), "add amem")
    pdh.PdhCollectQueryData(q)
    time.sleep(interval)

    cost_ms: list[float] = []
    instances: list[int] = []
    util_acc: dict[tuple[int, str, str], list[float]] = defaultdict(list)
    adapter_util: dict[tuple[str, str], list[float]] = defaultdict(list)
    pmem: dict[tuple[int, str], float] = {}
    amem: dict[str, float] = {}
    cpu0, wall0 = time.process_time(), time.perf_counter()
    for _ in range(samples):
        t0 = time.perf_counter()
        check(pdh.PdhCollectQueryData(q), "collect")
        eng = read_array(c_eng, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100)
        pm = read_array(c_pmem, PDH_FMT_DOUBLE)
        am = read_array(c_amem, PDH_FMT_DOUBLE)
        cost_ms.append((time.perf_counter() - t0) * 1000)
        instances.append(len(eng))
        per_adapter: dict[tuple[str, str], float] = defaultdict(float)
        for name, v in eng.items():
            m = ENG_RE.match(name)
            if m:
                pid, luid, et = int(m[1]), m[2].upper(), m[3]
                util_acc[(pid, luid, et)].append(v)
                per_adapter[(luid, et)] += v
        for k, v in per_adapter.items():
            adapter_util[k].append(v)
        for name, v in pm.items():
            m = PMEM_RE.match(name)
            if m:
                pmem[(int(m[1]), m[2].upper())] = v
        for name, v in am.items():
            m = AMEM_RE.match(name)
            if m:
                amem[m[1].upper()] = v
        time.sleep(max(0.0, interval - (time.perf_counter() - t0)))
    cpu_pct = (time.process_time() - cpu0) / (time.perf_counter() - wall0) * 100
    pdh.PdhCloseQuery(q)

    def lname(luid: str) -> str:
        return luid_name.get(luid, luid)

    # adapter overview: max over engine types of mean utilization (Task-Manager logic)
    overview: dict[str, Any] = {}
    for (luid, et), vals in adapter_util.items():
        o = overview.setdefault(lname(luid), {"engines": {}, "dedicated_used_mib": round(amem.get(luid, 0) / 2**20)})
        o["engines"][et] = round(statistics.mean(vals), 1)
    for o in overview.values():
        o["util_pct"] = max(o["engines"].values(), default=0.0)
        o["engines"] = {k: v for k, v in sorted(o["engines"].items(), key=lambda kv: -kv[1]) if v >= 0.1}

    # per process attribution
    procs: dict[int, dict[str, Any]] = defaultdict(lambda: {"adapters": defaultdict(lambda: {"engines": {}, "vram_mib": 0})})
    for (pid, luid, et), vals in util_acc.items():
        mean = statistics.mean(vals)
        if mean >= 0.05:
            procs[pid]["adapters"][lname(luid)]["engines"][et] = round(mean, 2)
    for (pid, luid), v in pmem.items():
        if v >= 16 * 2**20:
            procs[pid]["adapters"][lname(luid)]["vram_mib"] = round(v / 2**20)
    report = []
    for pid, p in procs.items():
        adapters_out = {k: dict(v) for k, v in p["adapters"].items()}
        if not adapters_out:
            continue
        score = {k: sum(e for t, e in v["engines"].items() if t in ("3D",) or t.startswith("Compute")) for k, v in adapters_out.items()}
        top = max(score, key=lambda k: score[k])
        render = top if score[top] >= 0.5 else None
        report.append({"pid": pid, "name": proc_name(pid), "observed_render_gpu": render or "idle/unbestimmt", "adapters": adapters_out, "_score": sum(score.values())})
    report.sort(key=lambda r: -r["_score"])
    for r in report:
        r.pop("_score")

    print(json.dumps({
        "cost": {
            "samples": samples,
            "engine_instances_avg": round(statistics.mean(instances)),
            "collect_plus_format_ms_median": round(statistics.median(cost_ms), 2),
            "collect_plus_format_ms_max": round(max(cost_ms), 2),
            "process_cpu_pct_at_interval": round(cpu_pct, 2),
        },
        "adapters": overview,
        "top_processes": report[:12],
        "unity": [r for r in report if r["name"].lower().startswith("unity")],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
