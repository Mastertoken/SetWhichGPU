"""Steam library: libraryfolders.vdf, appmanifest_*.acf and the binary appinfo.vdf (read-only).

appinfo.vdf v29 (magic 0x07564429) layout::

    u32 magic, u32 universe, i64 string_table_offset
    entries: u32 appid (0 = end), u32 size, u32 state, u32 last_updated, u64 pics_token,
             20 B sha1, u32 change_number, 20 B binary sha1, binary KeyValues (keys = string-table index)
    string table: u32 count, count × NUL-terminated UTF-8 strings

Unknown/older formats are rejected gracefully → the caller falls back to the exe heuristic.
"""

from __future__ import annotations

import logging
import re
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

APPINFO_MAGIC_V29 = 0x07564429
_ENTRY_HEADER = struct.Struct("<IIIIQ20sI20s")  # appid … binary sha1 (after appid: size+…)

# Binary KeyValues types
_KV_MAP, _KV_STRING, _KV_INT32, _KV_FLOAT, _KV_PTR, _KV_WSTRING, _KV_COLOR, _KV_UINT64, _KV_END = (
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
)  # fmt: skip
_KV_INT64 = 0x0A

#: Apps that are tools/runtimes/drivers, not games.
NON_GAME_APPIDS = frozenset({"228980", "719950"})  # Steamworks Redistributables, WMR for SteamVR driver
#: Known render processes where the launch exe is only a starter.
KNOWN_RENDER_EXE = {"250820": r"bin\win64\vrcompositor.exe"}  # SteamVR compositor


# ----------------------------------------------------------------------------- text VDF (ACF)
def _vdf_values(text: str, key: str) -> list[str]:
    return [m.replace("\\\\", "\\") for m in re.findall(rf'"{re.escape(key)}"\s+"([^"]*)"', text)]


def library_paths(steam_root: Path) -> list[Path]:
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [steam_root]
    paths = [Path(p) for p in _vdf_values(text, "path")]
    return paths or [steam_root]


def read_manifest(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out = {}
    for key in ("appid", "name", "installdir"):
        values = _vdf_values(text, key)
        if not values:
            return None
        out[key] = values[0]
    return out


# ----------------------------------------------------------------------------- binary appinfo
class _Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def unpack(self, fmt: str) -> Any:
        s = struct.calcsize(fmt)
        v = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += s
        return v

    def cstr(self) -> str:
        end = self.data.index(b"\x00", self.pos)
        s = self.data[self.pos : end].decode("utf-8", errors="replace")
        self.pos = end + 1
        return s


def _read_kv(r: _Reader, keys: list[str]) -> dict[str, Any]:
    node: dict[str, Any] = {}
    while True:
        t = r.u8()
        if t == _KV_END:
            return node
        key = keys[r.unpack("<I")]
        if t == _KV_MAP:
            node[key] = _read_kv(r, keys)
        elif t == _KV_STRING:
            node[key] = r.cstr()
        elif t in (_KV_INT32, _KV_PTR, _KV_COLOR):
            node[key] = r.unpack("<i")
        elif t == _KV_FLOAT:
            node[key] = r.unpack("<f")
        elif t in (_KV_UINT64, _KV_INT64):
            node[key] = r.unpack("<Q")
        else:
            raise ValueError(f"unsupported KeyValues type 0x{t:02X}")


def parse_appinfo(data: bytes) -> dict[str, dict[str, Any]]:
    """appid → 'appinfo' KeyValues tree. Raises ValueError for unsupported formats."""
    if len(data) < 16:
        raise ValueError("appinfo.vdf too short")
    magic, _universe, table_offset = struct.unpack_from("<IIq", data, 0)
    if magic != APPINFO_MAGIC_V29:
        raise ValueError(f"unsupported appinfo.vdf version 0x{magic:08X}")
    t = _Reader(data, table_offset)
    keys = [t.cstr() for _ in range(t.unpack("<I"))]
    r = _Reader(data, 16)
    apps: dict[str, dict[str, Any]] = {}
    while r.pos < table_offset:
        appid = r.unpack("<I")
        if appid == 0:
            break
        size = r.unpack("<I")
        entry_end = r.pos + size
        r.pos += _ENTRY_HEADER.size - 8  # state … binary sha1 (appid + size already consumed)
        if r.u8() != _KV_MAP:
            r.pos = entry_end
            continue
        r.unpack("<I")  # root key ("appinfo")
        try:
            apps[str(appid)] = _read_kv(r, keys)
        except (ValueError, IndexError, struct.error):
            log.debug("skipping unparsable appinfo entry %s", appid)
        r.pos = entry_end
    return apps


def launch_executable(appinfo: dict[str, Any]) -> str | None:
    """Relative exe path of the default Windows launch option (``config/launch``)."""
    launches = appinfo.get("config", {}).get("launch", {})
    if not isinstance(launches, dict):
        return None
    candidates: list[tuple[int, str]] = []
    for idx, opt in launches.items():
        if not isinstance(opt, dict):
            continue
        exe = str(opt.get("executable", ""))
        oslist = (
            str(opt.get("config", {}).get("oslist", "windows")) if isinstance(opt.get("config"), dict) else "windows"
        )
        if not exe.lower().endswith(".exe") or (oslist and "windows" not in oslist):
            continue
        kind = str(opt.get("type", "default")).lower()
        rank = 0 if kind in ("default", "none", "") else 1
        candidates.append((rank * 100 + (int(idx) if str(idx).isdigit() else 99), exe.replace("/", "\\")))
    return min(candidates)[1] if candidates else None


def load_appinfo(steam_root: Path) -> dict[str, dict[str, Any]]:
    try:
        return parse_appinfo((steam_root / "appcache" / "appinfo.vdf").read_bytes())
    except (OSError, ValueError) as e:
        log.warning("Steam appinfo.vdf not usable (%s) – falling back to exe heuristic", e)
        return {}


def iter_manifests(libraries: list[Path]) -> Iterator[tuple[Path, dict[str, str]]]:
    for lib in libraries:
        for f in sorted((lib / "steamapps").glob("appmanifest_*.acf")):
            m = read_manifest(f)
            if m is not None:
                yield lib, m
