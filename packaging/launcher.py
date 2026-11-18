"""PyInstaller entry point for SetWhichGPU.exe (same as ``python -m gpucc``)."""

from gpucc.__main__ import main

raise SystemExit(main())
