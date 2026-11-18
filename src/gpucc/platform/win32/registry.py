"""HKCU registry access. Writes are limited to the keys allowed by AGENTS.md §4."""

from __future__ import annotations

import winreg

USER_GPU_PREFERENCES = r"Software\Microsoft\DirectX\UserGpuPreferences"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class UserGpuPreferenceRegistry:
    """HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences (value name = full exe path)."""

    def __init__(self, key_path: str = USER_GPU_PREFERENCES) -> None:
        self._key_path = key_path  # overridable for tests (HKCU\\Software\\SetWhichGPUTest)

    def read(self, exe_path: str) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path) as key:
                value, kind = winreg.QueryValueEx(key, exe_path)
        except OSError:
            return None
        return str(value) if kind == winreg.REG_SZ else None

    def entries(self) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, kind = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    if kind == winreg.REG_SZ and name and name != "DirectXUserGlobalSettings":
                        out[str(name)] = str(value)
                    i += 1
        except OSError:
            pass
        return out

    def write(self, exe_path: str, value: str) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, value)

    def delete(self, exe_path: str) -> None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, exe_path)
        except FileNotFoundError:
            pass


# Backwards-compatible name used in phase 2.
UserGpuPreferenceReader = UserGpuPreferenceRegistry


class AutostartEntry:
    """HKCU\\…\\CurrentVersion\\Run entry for this application."""

    def __init__(self, name: str = "SetWhichGPU", key_path: str = RUN_KEY) -> None:
        self._name = name
        self._key_path = key_path

    def command(self) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path) as key:
                return str(winreg.QueryValueEx(key, self._name)[0])
        except OSError:
            return None

    def enable(self, command: str) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, self._name, 0, winreg.REG_SZ, command)

    def disable(self) -> None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self._name)
        except FileNotFoundError:
            pass
