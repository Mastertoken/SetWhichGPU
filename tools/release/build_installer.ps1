<#
.SYNOPSIS
  Builds dist\SetWhichGPU-<version>-setup.exe (PyInstaller one-folder build + Inno Setup).

.DESCRIPTION
  1. Checks (ruff, mypy, unit tests) unless -SkipChecks
  2. PyInstaller build from packaging\setwhichgpu.spec   -> build\pyi-dist\SetWhichGPU
  3. Smoke test of the frozen exe (imports and sub-command dispatch)
  4. License texts of all bundled components             -> build\licenses
  5. Inno Setup (packaging\setwhichgpu.iss)              -> dist\SetWhichGPU-<version>-setup.exe (+ .sha256)
  Requirements: uv, Inno Setup 6 (winget install JRSoftware.InnoSetup).
  Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.

.EXAMPLE
  .\tools\release\build_installer.ps1
#>
param([switch]$SkipChecks)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo
$env:UV_LINK_MODE = "copy"

function Invoke-Step([string]$Name, [scriptblock]$Block) {
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)" }
}

$version = ([regex]::Match((Get-Content src\gpucc\__init__.py -Raw), '__version__ = "([^"]+)"')).Groups[1].Value
if (-not $version) { throw "version not found in src\gpucc\__init__.py" }
Write-Host "SetWhichGPU $version" -ForegroundColor Green

$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }

Invoke-Step "uv sync" { uv sync --locked -q }
if (-not $SkipChecks) {
    Invoke-Step "ruff" { uv run ruff check . }
    Invoke-Step "mypy" { uv run mypy src }
    Invoke-Step "unit tests" { uv run pytest -q }
}

Invoke-Step "PyInstaller" {
    uv run pyinstaller --noconfirm --clean --log-level WARN --distpath build\pyi-dist --workpath build\pyi-work packaging\setwhichgpu.spec
}
$exe = Join-Path $repo "build\pyi-dist\SetWhichGPU\SetWhichGPU.exe"

# Smoke test: an invalid helper call must be rejected by argparse (exit 2) - proves the frozen
# interpreter starts, imports gpucc and dispatches sub-commands, without touching any device.
$p = Start-Process -FilePath $exe -ArgumentList "--gamemode-helper" -Wait -PassThru -WindowStyle Hidden
if ($p.ExitCode -ne 2) { throw "smoke test failed: '--gamemode-helper' without arguments returned $($p.ExitCode), expected 2" }
Write-Host "smoke test passed" -ForegroundColor Green

Invoke-Step "licenses" { uv run python tools\release\collect_licenses.py }
Invoke-Step "Inno Setup" { & $iscc /Q "/DAppVersion=$version" packaging\setwhichgpu.iss }

$setup = Join-Path $repo "dist\SetWhichGPU-$version-setup.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  SetWhichGPU-$version-setup.exe" | Out-File -Encoding ascii "$setup.sha256"
Write-Host ("Built {0} ({1:N1} MB)" -f $setup, ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green
Write-Host "SHA256 $hash"
