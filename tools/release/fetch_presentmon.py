"""Download the pinned Intel PresentMon console build into build/vendor/ (checksum-verified).

Used by build_installer.ps1 and for running from source (frame analysis, ADR-0004).
Usage: uv run python tools/release/fetch_presentmon.py
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from gpucc.analysis.presentmon import EXE_NAME, SHA256, VERSION  # noqa: E402

URL = f"https://github.com/GameTechDev/PresentMon/releases/download/v{VERSION}/PresentMon-{VERSION}-x64.exe"
TARGET = ROOT / "build" / "vendor" / EXE_NAME


def main() -> int:
    if TARGET.is_file() and hashlib.sha256(TARGET.read_bytes()).hexdigest() == SHA256:
        print(f"PresentMon {VERSION} already present")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading PresentMon {VERSION} …")
    with urllib.request.urlopen(URL, timeout=60) as r:
        data = r.read(64 << 20)
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        print(f"checksum mismatch: {digest}", file=sys.stderr)
        return 1
    TARGET.write_bytes(data)
    print(f"saved {TARGET} ({len(data) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
