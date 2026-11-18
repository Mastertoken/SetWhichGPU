"""Spike S6 end-to-end: preference -> app start -> observed GPU.

For each target GPU: write SpecificAdapter preference for the probe EXE (only that value),
start the probe with s6_d3d_load.py, read PDH process memory per adapter for its PID,
then restore the previous registry state. Usage: uv run python tools/spikes/s6_e2e.py
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
import winreg
from ctypes import wintypes as wt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s2_adapters import dxgi_adapters, kmt_info  # noqa: E402
from s5_s6_pdh import PDH_FMT_DOUBLE, PMEM_RE, check, pdh, read_array  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "build" / "probe" / "gpucc-dxgi-probe.exe"
KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
PYHOME = Path(sys.base_prefix)


def main() -> int:
    adapters, _ = dxgi_adapters()
    gpus = []
    luid_name = {}
    for a in adapters:
        if a["software"] or str(kmt_info(a["_luid"]).get("pci_address", "")).startswith("FFFFFFFF"):
            continue
        gpus.append(a)
        luid_name[a["luid"].upper()] = a["description"]

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
        try:
            previous = winreg.QueryValueEx(k, str(PROBE))[0]
        except OSError:
            previous = None
        results = []
        try:
            for g in gpus:
                value = f"SpecificAdapter={g['vendor_id']}&{g['device_id']}&{g['subsys_id']};GpuPreference=1073741824;"
                winreg.SetValueEx(k, str(PROBE), 0, winreg.REG_SZ, value)
                env = dict(os.environ, PYTHONHOME=str(PYHOME))
                p = subprocess.Popen([str(PROBE), str(ROOT / "tools/spikes/s6_d3d_load.py"), "6", "256"], stdout=subprocess.PIPE, text=True, env=env)
                info = json.loads(p.stdout.readline() if p.stdout else "{}")
                time.sleep(1.0)
                q, c = wt.HANDLE(), wt.HANDLE()
                check(pdh.PdhOpenQueryW(None, 0, ctypes.byref(q)), "open")
                check(pdh.PdhAddEnglishCounterW(q, r"\GPU Process Memory(*)\Dedicated Usage", 0, ctypes.byref(c)), "add")
                check(pdh.PdhCollectQueryData(q), "collect")
                mem = read_array(c, PDH_FMT_DOUBLE)
                pdh.PdhCloseQuery(q)
                observed = {}
                for name, v in mem.items():
                    m = PMEM_RE.match(name)
                    if m and int(m[1]) == info.get("pid") and v > 0:
                        observed[luid_name.get(m[2].upper(), m[2])] = round(v / 2**20)
                p.wait(timeout=30)
                top = max(observed, key=lambda n: observed[n]) if observed else None
                results.append({
                    "preference": g["description"],
                    "dxgi_default_in_app": info.get("dxgi_default_adapter"),
                    "observed_vram_mib_by_gpu": observed,
                    "observed_gpu": top,
                    "match": top == g["description"],
                })
        finally:
            if previous is None:
                winreg.DeleteValue(k, str(PROBE))
            else:
                winreg.SetValueEx(k, str(PROBE), 0, winreg.REG_SZ, previous)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
