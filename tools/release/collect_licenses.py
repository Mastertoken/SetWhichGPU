"""Copy the license texts of everything the installer ships into build/licenses/.

    uv run python tools/release/collect_licenses.py [--out build/licenses]

Bundled: Python (PSF), PySide6/shiboken6 (Qt for Python, LGPL-3.0), nvidia-ml-py (BSD-3-Clause) and the
PyInstaller bootloader (GPL-2.0 with bootloader exception). Fails if a license text is missing.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDORED = ROOT / "packaging" / "licenses"  # LGPL-3.0 / GPL-3.0 texts (PySide6 wheels do not contain them)
LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE)[^/]*$", re.IGNORECASE)

QT_NOTE = """Qt for Python (PySide6 {version}, shiboken6) is used under the GNU Lesser General Public License v3
(LGPL-3.0-only, full text in LGPL-3.0-only.txt, which incorporates GPL-3.0-only.txt).

SetWhichGPU uses the unmodified PySide6/Qt libraries as separate, dynamically loaded files in the
"_internal" folder of the installation; you may replace them with your own compatible build.
Source code of this exact version: https://download.qt.io/official_releases/QtForPython/pyside6/
and https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{version}
"""


def _dist_license_files(name: str) -> list[Path]:
    dist = metadata.distribution(name)
    return [
        Path(str(dist.locate_file(f)))
        for f in dist.files or ()
        if (".dist-info" in str(f) and LICENSE_FILE.search(str(f).replace("\\", "/").split("/")[-1]))
        or "/licenses/" in str(f).replace("\\", "/")
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "licenses")
    args = parser.parse_args()
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    # Python
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        raise SystemExit(f"Python license not found: {python_license}")
    target = args.out / f"Python-{sys.version.split()[0]}"
    target.mkdir()
    shutil.copy2(python_license, target / "LICENSE.txt")

    # Qt for Python
    version = metadata.version("PySide6_Essentials")
    target = args.out / f"PySide6-{version}"
    target.mkdir()
    for name in ("LGPL-3.0-only.txt", "GPL-3.0-only.txt"):
        shutil.copy2(VENDORED / name, target / name)
    for f in _dist_license_files("PySide6_Essentials") + _dist_license_files("shiboken6"):
        if not f.name.startswith("LicenseRef-Qt-Commercial"):  # we use Qt under the LGPL, not commercially
            shutil.copy2(f, target / f.name)
    (target / "README.txt").write_text(QT_NOTE.format(version=version), encoding="utf-8")

    # nvidia-ml-py: the BSD license text is the header of pynvml.py
    import pynvml

    header = []
    for line in Path(pynvml.__file__).read_text(encoding="utf-8").splitlines()[1:]:
        if line.startswith("#####"):
            break
        header.append(line.lstrip("#")[1:] if line.startswith("# ") else line.lstrip("#"))
    if not any("Redistribution and use" in h for h in header):
        raise SystemExit("nvidia-ml-py license header not found")
    target = args.out / f"nvidia-ml-py-{metadata.version('nvidia-ml-py')}"
    target.mkdir()
    (target / "LICENSE.txt").write_text("\n".join(header).strip() + "\n", encoding="utf-8")

    # PyInstaller bootloader
    files = _dist_license_files("pyinstaller")
    if not files:
        raise SystemExit("PyInstaller license not found")
    target = args.out / f"PyInstaller-{metadata.version('pyinstaller')}"
    target.mkdir()
    for f in files:
        shutil.copy2(f, target / f.name)

    for d in sorted(args.out.iterdir()):
        print(f"{d.name}: {', '.join(sorted(p.name for p in d.iterdir()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
