def test_only_our_own_autostart_entry_is_removed():
    from gpucc.uninstall import points_to

    exe = r"C:\Users\x\AppData\Local\Programs\SetWhichGPU\SetWhichGPU.exe"
    assert points_to(f'"{exe}"', exe)
    assert points_to(f'"{exe.upper()}" --minimized', exe)  # Windows paths are case-insensitive
    assert points_to(exe, exe)
    assert not points_to(r'"D:\Other\SetWhichGPU\SetWhichGPU.exe"', exe)  # another installation keeps its entry
    assert not points_to(r'"E:\repo\.venv\Scripts\pythonw.exe" -m gpucc', exe)  # source checkout
    assert not points_to(None, exe) and not points_to("", exe)
